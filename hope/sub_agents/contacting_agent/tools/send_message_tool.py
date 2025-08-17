import os
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

load_dotenv()


def send_message_tool(contact_number: str, message_body: str) -> str:
    """
    Sends a WhatsApp message to a specified contact number using Twilio.

    Args:
        contact_number (str): The recipient's phone number in E.164 format (e.g., "+14155238886").
        message_body (str): The content of the message to be sent.

    Returns:
        str: A confirmation message indicating success or an error message.
    """


    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER") 

    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        print("❌ Critical Error: Twilio credentials not found in .env file.")
        print("Please add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER to your .env file.")

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        print("✅ Twilio client initialized successfully.")
    except Exception as e:
        client = None
        print(f"❌ Failed to initialize Twilio client: {e}")

    if not client:
        return "Error: Twilio client is not initialized. Please check credentials."

    try:
        print(f"Attempting to send message to {contact_number}...")
        message = client.messages.create(
            from_=f'whatsapp:{TWILIO_PHONE_NUMBER}',
            body=message_body,
            to=f'whatsapp:{contact_number}'
        )
        success_message = f"Message sent successfully to {contact_number}. SID: {message.sid}"
        print(f"✅ {success_message}")
        return success_message
    except TwilioRestException as e:
        error_message = f"Failed to send message. Error: {e}"
        print(f"❌ {error_message}")
        return error_message
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        print(f"❌ {error_message}")
        return error_message

