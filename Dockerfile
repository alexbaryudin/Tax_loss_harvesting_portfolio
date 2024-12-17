# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the API port
EXPOSE 8000

# Define the command to run the application
CMD ["uvicorn", "FIFO_portf_snake_JsonArray:app", "--host", "0.0.0.0", "--port", "8000"]