"""Real OCI-backed implementation of :class:`~occfix.gateway.OciGateway`.

The heavy ``oci`` import is confined to :meth:`RealOciGateway.from_auth` and the
error-translation path so unit tests can inject fake clients without importing
the SDK object graph.
"""

from __future__ import annotations

from occfix.gateway import OciGateway
from occfix.models import (
    InstanceInfo,
    LaunchSpec,
    TransientError,
    VolumeInfo,
    error_for,
)


class RealOciGateway(OciGateway):
    """Gateway that talks to a live OCI tenancy via the ``oci`` SDK clients."""

    def __init__(
        self,
        compute,
        identity,
        network,
        blockstorage,
        *,
        retry_strategy=None,
    ) -> None:
        self._compute = compute
        self._identity = identity
        self._network = network
        self._blockstorage = blockstorage
        self._retry_strategy = retry_strategy

    @classmethod
    def from_auth(cls, auth) -> RealOciGateway:
        """Build a gateway with the four OCI clients derived from ``auth``."""

        import oci  # noqa: PLC0415 - lazy import keeps the SDK off the hot path

        from occfix.auth import build_oci_config_and_signer

        config, signer = build_oci_config_and_signer(auth)
        kwargs = {"signer": signer} if signer is not None else {}
        compute = oci.core.ComputeClient(config, **kwargs)
        identity = oci.identity.IdentityClient(config, **kwargs)
        network = oci.core.VirtualNetworkClient(config, **kwargs)
        blockstorage = oci.core.BlockstorageClient(config, **kwargs)
        return cls(compute, identity, network, blockstorage)

    # -- read APIs -------------------------------------------------------
    def list_availability_domains(self, compartment_id: str) -> list[str]:
        ads = self._identity.list_availability_domains(compartment_id=compartment_id).data
        return [ad.name for ad in ads]

    def list_volumes(self, compartment_id: str) -> list[VolumeInfo]:
        volumes = self._blockstorage.list_volumes(compartment_id=compartment_id).data
        return [_to_volume_info(v) for v in volumes]

    def list_boot_volumes(self, compartment_id: str, availability_domain: str) -> list[VolumeInfo]:
        boot_volumes = self._blockstorage.list_boot_volumes(
            compartment_id=compartment_id,
            availability_domain=availability_domain.strip(),
        ).data
        return [_to_volume_info(v) for v in boot_volumes]

    def list_instances(self, compartment_id: str) -> list[InstanceInfo]:
        instances = self._compute.list_instances(compartment_id=compartment_id).data
        return [_to_instance_info(i) for i in instances]

    def get_tenancy_name(self, tenancy_id: str) -> str:
        try:
            return self._identity.get_tenancy(tenancy_id).data.name
        except Exception:
            return tenancy_id

    # -- launch ----------------------------------------------------------
    def launch_instance(self, spec: LaunchSpec, availability_domain: str, retry_token: str) -> str:
        import base64
        import oci  # noqa: PLC0415 - lazy import keeps the SDK off the hot path

        metadata: dict[str, str] = {"ssh_authorized_keys": spec.ssh_keys}
        if spec.user_data:
            ud_bytes = spec.user_data.encode("utf-8") if isinstance(spec.user_data, str) else spec.user_data
            try:
                base64.b64decode(ud_bytes, validate=True)
                metadata["user_data"] = spec.user_data if isinstance(spec.user_data, str) else ud_bytes.decode("ascii")
            except Exception:
                metadata["user_data"] = base64.b64encode(ud_bytes).decode("ascii")
        elif spec.shape == "VM.Standard.E2.1.Micro" or spec.machine_type.upper() in ("AMD", "X86"):
            # Automated 8 GB swap allocation + kernel tuning + anti-idle heartbeat cron
            cloud_init_script = (
                "#!/bin/bash\n"
                "fallocate -l 8G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=8192\n"
                "chmod 600 /swapfile\n"
                "mkswap /swapfile\n"
                "swapon /swapfile\n"
                "echo '/swapfile none swap sw 0 0' >> /etc/fstab\n"
                "sysctl vm.swappiness=60\n"
                "sysctl vm.vfs_cache_pressure=50\n"
                "echo 'vm.swappiness=60' >> /etc/sysctl.conf\n"
                "echo 'vm.vfs_cache_pressure=50' >> /etc/sysctl.conf\n"
                "(crontab -l 2>/dev/null; echo '*/15 * * * * dd if=/dev/urandom of=/dev/null bs=1M count=20 status=none; ping -c 3 1.1.1.1 >/dev/null 2>&1') | crontab -\n"
            )
            metadata["user_data"] = base64.b64encode(cloud_init_script.encode("utf-8")).decode("ascii")

        shape_config = (
            oci.core.models.LaunchInstanceShapeConfigDetails(
                ocpus=spec.ocpus,
                memory_in_gbs=spec.memory,
            )
            if spec.is_flex()
            else None
        )

        details = oci.core.models.LaunchInstanceDetails(
            metadata=metadata,
            availability_domain=availability_domain.strip(),
            compartment_id=spec.compartment_id,
            shape=spec.shape,
            display_name=spec.display_name,
            source_details=_source_details(oci, spec),
            create_vnic_details=oci.core.models.CreateVnicDetails(
                subnet_id=spec.subnet_id,
                assign_public_ip=True,
            ),
            shape_config=shape_config,
        )

        try:
            response = self._compute.launch_instance(details, opc_retry_token=retry_token)
        except oci.exceptions.ServiceError as exc:
            raise error_for(
                exc.message,
                code=exc.code,
                status=exc.status,
                retry_after=_retry_after(getattr(exc, "headers", None)),
            ) from exc
        except Exception as exc:
            raise TransientError(str(exc), code="Unexpected") from exc

        return response.data.id

    def get_public_ip(self, compartment_id: str, instance_id: str) -> str | None:
        try:
            import oci  # noqa: PLC0415

            vnic = self._compute.list_vnic_attachments(
                compartment_id=compartment_id,
                instance_id=instance_id,
            ).data[0]
            private_ip = self._network.list_private_ips(vnic_id=vnic.vnic_id).data[0].id
            return self._network.get_public_ip_by_private_ip_id(
                oci.core.models.GetPublicIpByPrivateIpIdDetails(private_ip_id=private_ip)
            ).data.ip_address
        except Exception:
            return None


def _source_details(oci, spec: LaunchSpec):
    if spec.uses_boot_volume():
        return oci.core.models.InstanceSourceViaBootVolumeDetails(
            source_type="bootVolume",
            boot_volume_id=spec.boot_volume_id,
        )
    return oci.core.models.InstanceSourceViaImageDetails(
        source_type="image",
        image_id=spec.image_id,
        boot_volume_size_in_gbs=spec.boot_volume_size,
    )


def _to_volume_info(volume) -> VolumeInfo:
    return VolumeInfo(
        size_in_gbs=int(volume.size_in_gbs),
        lifecycle_state=volume.lifecycle_state,
    )


def _to_instance_info(instance) -> InstanceInfo:
    shape_config = getattr(instance, "shape_config", None)
    ocpus = float(getattr(shape_config, "ocpus", 0.0) or 0.0)
    memory = float(getattr(shape_config, "memory_in_gbs", 0.0) or 0.0)
    return InstanceInfo(
        display_name=instance.display_name,
        lifecycle_state=instance.lifecycle_state,
        shape=instance.shape or "",
        ocpus=ocpus,
        memory_in_gbs=memory,
    )


def _retry_after(headers) -> float | None:
    if not headers:
        return None
    getter = getattr(headers, "get", None)
    raw = getter("retry-after") if callable(getter) else None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
