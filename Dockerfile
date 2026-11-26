FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir cryptography
COPY node.py contract.py client.py ./
EXPOSE 5000
CMD ["python", "node.py", "5000", ""]
