FROM python:3.11-alpine

# Set up environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Create and set the working directory
WORKDIR /app

# Copy only the requirements file first to leverage Docker caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application code
COPY . .

# Set the user to run the application
USER root

# Create a directory for writable files and set permissions
RUN chmod -R 777 /app

# Expose the port your application will run on
EXPOSE 5001

# Specify the command to run on container start
CMD [ "python3", "app.py"]