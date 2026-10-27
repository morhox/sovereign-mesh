FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn pydantic
COPY mesh_node.py .
EXPOSE 8000
CMD ["python", "mesh_node.py"]
