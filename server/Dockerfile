FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir websockets==17.2
COPY relay.py .
COPY mobile ./mobile
USER 65534:65534
ENV RELAY_HOST=0.0.0.0
EXPOSE 8765
CMD ["python", "relay.py"]
