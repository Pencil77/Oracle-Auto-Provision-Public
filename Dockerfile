FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN echo '#!/bin/sh\n\
cp /etc/secrets/* /app/ 2>/dev/null || true\n\
python3 dummy_server.py &\n\
python3 bot.py\n\
wait -n' > start.sh

RUN chmod +x start.sh

EXPOSE 8000
CMD ["./start.sh"]
