import os
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

load_dotenv()

def receive_message_tool() -> str:
    """
    Retrieves the most recent incoming WhatsApp message from Twilio.

    Returns:
        str: The content and sender of the last message, or a status message if none are found.
    """

    try:
        print("Checking for new incoming messages...")

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

        messages = client.messages.list(
            to=f'whatsapp:{TWILIO_PHONE_NUMBER}',
            limit=1
        )

        if not messages:
            print("No new messages found.")
            return "You have no new messages."

        latest_message = messages[0]
        response = f"New message from {latest_message.from_}: '{latest_message.body}'"
        print(f"✅ Found message: {response}")
        return response
    except TwilioRestException as e:
        error_message = f"Failed to retrieve messages. Error: {e}"
        print(f"❌ {error_message}")
        return error_message
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        print(f"❌ {error_message}")
        return error_message

