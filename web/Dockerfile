FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py lab.html flag6_xxe.txt flag7_jwt.txt flag8_traversal.txt ./
COPY uploads/ ./uploads/
COPY data/ ./data/
EXPOSE 80
CMD ["python", "app.py"]