# # Use an official Python runtime as the base image
# FROM python:3.8

# # Set the working directory in the container
# WORKDIR /app

# # Copy the current directory contents into the container at /app
# COPY . /app

# # Install any needed dependencies specified in requirements.txt
# RUN pip install --no-cache-dir -r requirements.txt

# # Make port 80 available to the world outside this container
# EXPOSE 802

# # Run app.py when the container launches
# CMD ["python", "app2.py"]


FROM ubuntu:22.04

# Install necessary packages
RUN apt-get update && apt-get install -y \
    apt-utils \
    libsm6 \
    libxrender1 \
    libfontconfig1 \
    libice6 \
    libglib2.0-0 \
    python3-pip \
    libreoffice

# Copy the application code
WORKDIR /app

# Install Python dependencies
COPY . /app

RUN pip3 install -r requirements.txt

# Expose the port the app runs on
EXPOSE 815

# Set the entry point
CMD ["python3", "app2.py"]