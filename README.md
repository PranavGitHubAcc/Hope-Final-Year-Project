# Hope-Final-Year-Project

This project is a system for Facial Emotion Recognition (FER), designed to work with a Raspberry Pi. It features a modular architecture where different components handle specific parts of the workflow, from capturing images to recognizing emotions.

## Architecture Overview

The system operates in a sequential flow:

1.  **`rpi-interface`**: Captures image data from a camera connected to a Raspberry Pi.
2.  **`middleware`**: Receives the image data and forwards it to the processing service.
3.  **`fer-service`**: Analyzes the image using a machine learning model to detect and classify facial emotions.
4.  **`main.py`**: The central script that initializes and orchestrates these components.

## Component Descriptions

### `main.py`

The main entry point for the application. It is responsible for starting all the services and managing the overall application lifecycle.

### `rpi-interface/`

This module contains the code that interacts directly with the Raspberry Pi hardware. Its primary function is to capture video or image frames from a camera and publish them to the middleware.

### `middleware/`

This component serves as a communication bridge between the `rpi-interface` and the `fer-service`. It may use a message broker (like MQTT or RabbitMQ) to handle data transmission, ensuring that image data from the Pi is reliably delivered to the emotion recognition service.

### `fer-service/`

The core of the application, this service performs the Facial Emotion Recognition. It receives an image from the middleware, processes it to detect a face, and then uses a deep learning model to predict the emotion being displayed.

### `hope_finetuned/`

This directory contains the trained machine learning model files. The model has been fine-tuned specifically for the task of emotion recognition and is loaded by the `fer-service` to make predictions.