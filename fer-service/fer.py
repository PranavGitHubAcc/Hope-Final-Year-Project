#!/usr/bin/env python3
# Raspberry Pi Remote Emotion Detection System

import socket
import pickle
import struct
import cv2
import numpy as np
import tensorflow as tf
from deepface import DeepFace
from collections import Counter, deque
import time
import pandas as pd
import os
from datetime import datetime

# Enable TensorFlow GPU for DeepFace
for gpu in tf.config.experimental.list_physical_devices('GPU'):
    tf.config.experimental.set_memory_growth(gpu, True)

class CameraClient:
    def __init__(self, pi_ip, port=9999):
        self.pi_ip = pi_ip
        self.port = port
        self.socket = None
        self.data = b""
        self.payload_size = struct.calcsize("!I")  # 4-byte size header

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.pi_ip, self.port))
            self.socket.settimeout(None)
            print(f"✅ Connected to Raspberry Pi at {self.pi_ip}:{self.port}")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False

    def receive_frame(self):
        try:
            # Read message size (4 bytes)
            while len(self.data) < self.payload_size:
                packet = self.socket.recv(4096)
                if not packet:
                    return None
                self.data += packet

            packed_msg_size = self.data[:self.payload_size]
            self.data = self.data[self.payload_size:]
            msg_size = struct.unpack("!I", packed_msg_size)[0]

            # Read frame data
            while len(self.data) < msg_size:
                packet = self.socket.recv(4096)
                if not packet:
                    return None
                self.data += packet

            frame_data = self.data[:msg_size]
            self.data = self.data[msg_size:]

            # Decode frame
            encoded_img = pickle.loads(frame_data)
            frame = cv2.imdecode(encoded_img, cv2.IMREAD_COLOR)
            return frame

        except Exception as e:
            print(f"⚠️ Error receiving frame: {e}")
            return None

    def close(self):
        if self.socket:
            self.socket.close()

# Load YuNet face detection model (CPU only)
try:
    face_detector = cv2.FaceDetectorYN.create("face_detection_yunet_2023mar.onnx", "", (640, 480))
    print("✅ YuNet face detection model loaded successfully")
except Exception as e:
    print(f"❌ Error loading face detection model: {e}")
    print("Please ensure 'face_detection_yunet_2023mar.onnx' is in the current directory")
    exit()

# Get Raspberry Pi IP address
print("Find your Pi's IP address by running 'hostname -I' on the Pi")
PI_IP = input("Enter Pi IP address: ").strip()

# Initialize camera client
camera_client = CameraClient(PI_IP)
if not camera_client.connect():
    print("❌ Failed to connect to Raspberry Pi. Exiting...")
    exit()

# Create directory for storing emotion data if it doesn't exist
data_dir = "emotion_data"
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# Create a directory for archives if it doesn't exist
archive_dir = f"{data_dir}/archives"
if not os.path.exists(archive_dir):
    os.makedirs(archive_dir)

# Use fixed filenames for consistent access
excel_filename = f"{data_dir}/emotions_data.xlsx"
summary_filename = f"{data_dir}/emotions_summary.xlsx"

# Prepare DataFrame for storing emotion data
columns = ['timestamp', 'datetime', 'dominant_emotion', 'confidence']
# Add columns for all possible emotions to track their scores
all_emotions = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']
for emotion in all_emotions:
    columns.append(f"{emotion}_score")

emotion_df = pd.DataFrame(columns=columns)
last_save_time = time.time()
save_interval = 5  # Save to Excel every 5 seconds

# Data management settings
last_manage_time = time.time()
manage_interval = 60  # Manage data size every 60 seconds
max_rows = 3000  # Maximum rows to keep in active DataFrame
buffer_seconds = 30  # Always keep the last 30 seconds of data

# Control logging frequency
logging_interval = 0.5  # Log emotion data every 0.5 seconds
last_log_time = time.time()

# Function to manage data size with rolling buffer
def manage_data_size(df, max_rows=3000, buffer_seconds=30):
    """
    Maintains a rolling buffer of recent data while archiving older data
    
    Args:
        df: Emotion DataFrame
        max_rows: Maximum number of rows to keep in active DataFrame
        buffer_seconds: Number of seconds of most recent data to always keep
        
    Returns:
        DataFrame: DataFrame with managed size
    """
    if len(df) <= max_rows:
        return df  # No need to trim if under max size
    
    # Always keep the most recent buffer_seconds of data
    current_time = time.time()
    buffer_start_time = current_time - buffer_seconds
    
    # Split data into recent (keep) and older (archive)
    recent_data = df[df['timestamp'] >= buffer_start_time].copy()
    older_data = df[df['timestamp'] < buffer_start_time].copy()
    
    # Archive the older data
    timestamp_str = datetime.fromtimestamp(time.time()).strftime("%Y%m%d_%H%M%S")
    archive_filename = f"{archive_dir}/archive_{timestamp_str}.xlsx"
    older_data.to_excel(archive_filename, index=False)
    print(f"📁 Archived {len(older_data)} older records to {archive_filename}")
    
    # If recent data is still too large, keep only the most recent max_rows
    if len(recent_data) > max_rows:
        recent_data = recent_data.sort_values('timestamp', ascending=False).head(max_rows)
        print(f"⚠️ Trimmed recent data to {max_rows} rows")
    
    return recent_data

# Function to summarize emotions for a time range
def get_dominant_emotion_for_timerange(df, start_time, end_time):
    """
    Get the dominant emotion for a specific time range from the emotion DataFrame.
    
    Args:
        df: Emotion DataFrame
        start_time: Start timestamp
        end_time: End timestamp
        
    Returns:
        dict: Contains dominant emotion, confidence, and all emotion scores
    """
    # Filter dataframe for the time range
    time_range_df = df[(df['timestamp'] >= start_time) & (df['timestamp'] <= end_time)]
    
    if time_range_df.empty:
        return {"dominant_emotion": "unknown", "confidence": 0, "emotion_scores": {}}
    
    # Calculate average scores for each emotion
    emotion_scores = {}
    for emotion in all_emotions:
        emotion_scores[emotion] = time_range_df[f"{emotion}_score"].mean()
    
    # Apply weighting factors to prioritize non-neutral emotions
    weighted_scores = emotion_scores.copy()
    for emotion in emotion_scores:
        boost = {
            "sad": 2.0,
            "happy": 2.0,
            "surprise": 1.5,
            "angry": 1.5,
            "disgust": 1.5,
            "fear": 1.5,
            "neutral": 1.0
        }.get(emotion, 1.0)
        weighted_scores[emotion] *= boost
    
    # Find dominant emotion based on weighted scores
    dominant_emotion = max(weighted_scores, key=weighted_scores.get)
    confidence = weighted_scores[dominant_emotion]
    
    # Create detailed report including frame count and time duration
    frame_count = len(time_range_df)
    duration = end_time - start_time
    
    result = {
        "dominant_emotion": dominant_emotion,
        "confidence": confidence,
        "emotion_scores": emotion_scores,
        "weighted_scores": weighted_scores,
        "frame_count": frame_count,
        "duration_seconds": duration,
        "start_time": start_time,
        "end_time": end_time
    }
    
    return result

# Save current emotion data to Excel file
def save_to_excel(df, filename):
    try:
        df.to_excel(filename, index=False)
        print(f"💾 Data saved to {filename}")
    except Exception as e:
        print(f"❌ Error saving to Excel: {e}")

# Create a summary Excel with time ranges
def create_summary_excel(df, filename, period_seconds=1):
    """Create a summary Excel with emotions averaged over specified time periods"""
    if df.empty:
        print("⚠️ No data to summarize")
        return
    
    # Get the time range of the data
    min_time = df['timestamp'].min()
    max_time = df['timestamp'].max()
    
    summary_data = []
    current_time = min_time
    
    # Process in chunks of period_seconds
    while current_time < max_time:
        end_period = current_time + period_seconds
        
        # Get dominant emotion for this period
        result = get_dominant_emotion_for_timerange(df, current_time, end_period)
        
        if result.get("frame_count", 0) > 0:
            summary_data.append({
                'start_time': current_time,
                'end_time': end_period,
                'datetime': datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S"),
                'dominant_emotion': result["dominant_emotion"],
                'confidence': result["confidence"],
                'frame_count': result["frame_count"]
            })
        
        current_time = end_period
    
    # Create and save summary DataFrame
    if summary_data:
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(filename, index=False)
        print(f"📊 Summary data saved to {filename}")
        return summary_df
    else:
        print("⚠️ No summary data generated")
        return None

# Define analyze_emotions function before it's referenced
def analyze_emotions(emotion_history):
    """
    Advanced emotion analysis that accounts for:
    1. Non-neutral emotions having more significance
    2. High confidence emotions carrying more weight
    3. Duration of emotions
    """
    if not emotion_history:
        print("⚠️ No emotions recorded.")
        return
    
    # Create basic counters
    emotion_counts = Counter()
    for entry in emotion_history:
        emotion_counts[entry['emotion']] += 1
    
    # Calculate time spent in each emotion (approximate)
    total_entries = len(emotion_history)
    time_per_entry = 10 / total_entries if total_entries > 0 else 0
    emotion_durations = {emotion: count * time_per_entry for emotion, count in emotion_counts.items()}
    
    # Create weighted analysis that prioritizes non-neutral emotions
    weighted_emotions = {}
    neutral_weight = 0.3  # Further reduced neutral weight to prioritize other emotions
    
    for entry in emotion_history:
        emotion = entry['emotion']
        confidence = entry['confidence']
        weight = neutral_weight if emotion == 'neutral' else 1.5  # Increased weight for non-neutral emotions
        if emotion not in weighted_emotions:
            weighted_emotions[emotion] = 0
        weighted_emotions[emotion] += weight * confidence
    
    # Find most common, most significant, and highest weighted emotions
    most_frequent = emotion_counts.most_common(1)[0][0] if emotion_counts else None
    longest_duration = max(emotion_durations.items(), key=lambda x: x[1])[0] if emotion_durations else None
    most_significant = max(weighted_emotions.items(), key=lambda x: x[1])[0] if weighted_emotions else None
    
    # Print detailed analysis
    print("\n📊 Emotion Analysis Results:")
    print(f"Total frames analyzed: {len(emotion_history)}")
    
    print("\n⏱️ Approximate duration of each emotion:")
    for emotion, duration in sorted(emotion_durations.items(), key=lambda x: x[1], reverse=True):
        percentage = (duration / 10) * 100
        print(f"  {emotion}: {duration:.1f}s ({percentage:.1f}%)")
    
    print("\n🔍 Analysis based on different methods:")
    print(f"  Most frequent emotion: {most_frequent}")
    print(f"  Longest duration emotion: {longest_duration}")
    print(f"  Most significant emotion (weighted by intensity and non-neutrality): {most_significant}")
    
    # Make final recommendation with even stronger bias against neutral
    if most_significant != 'neutral' and weighted_emotions.get(most_significant, 0) > weighted_emotions.get('neutral', 0) * 0.6:  # Reduced threshold
        print(f"\n✅ Recommended emotion to consider: {most_significant}")
        print("   (This accounts for brief but meaningful emotional responses)")
    else:
        print(f"\n✅ Recommended emotion to consider: {longest_duration}")
        print("   (This represents the dominant emotional state during recording)")

# Voice recording markers
voice_recording = False
voice_start_time = 0
voice_segments = []  # Store voice segments with start/end times and dominant emotions

# Emotion tracking with slower logging
recording = False
emotion_history = deque()  # Store emotion data with timestamps
start_time = 0
recording_duration = 10  # Duration in seconds

print("\n📌 REMOTE EMOTION DETECTION FROM RASPBERRY PI")
print("=" * 50)
print("📌 Press 's' to START recording emotions for 10 seconds.")
print("📌 Press 'e' to manually STOP recording and see results.")
print("📌 Press 'v' to START/STOP voice recording marker.")
print("📌 Press 'c' to CLEAR Excel data and start fresh.")
print("📌 Press 'a' to ANALYZE and create summary.")
print("📌 Press 'q' to EXIT and save all data.")
print("📌 Press 'r' to RECONNECT to Raspberry Pi.\n")
print(f"📊 Emotion data is being logged every {logging_interval} seconds to: {excel_filename}")
print(f"⚠️ Data will be managed every {manage_interval} seconds, keeping the last {buffer_seconds} seconds.\n")

continuous_logging = True  # Always log emotions regardless of recording state
connection_lost = False

try:
    while True:
        # Receive frame from Raspberry Pi
        frame = camera_client.receive_frame()
        if frame is None:
            if not connection_lost:
                print("❌ Lost connection to Raspberry Pi. Press 'r' to reconnect or 'q' to quit.")
                connection_lost = True
            
            # Show a black frame with connection status
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "CONNECTION LOST", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
            cv2.putText(frame, "Press 'r' to reconnect", (180, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow("Pi Camera - Emotion Detection", frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('r'):
                print("🔄 Attempting to reconnect...")
                camera_client.close()
                if camera_client.connect():
                    connection_lost = False
                    continue
            elif key == ord('q'):
                break
            continue
        
        # Reset connection status if we successfully received a frame
        if connection_lost:
            connection_lost = False
            print("✅ Connection restored!")

        current_time = time.time()
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Resize frame for face detection if needed
        height, width = frame.shape[:2]
        face_detector.setInputSize((width, height))
        
        _, faces = face_detector.detect(frame)
        
        # Check if it's time to manage data size (every minute)
        if current_time - last_manage_time >= manage_interval:
            if not emotion_df.empty:
                # Before managing size, create a summary of the data
                print(f"\n⏱️ Managing data after {manage_interval} seconds")
                create_summary_excel(emotion_df, summary_filename, period_seconds=1)
                
                # Store any active voice segment information
                if voice_recording:
                    voice_emotion = get_dominant_emotion_for_timerange(emotion_df, voice_start_time, current_time)
                    voice_segments.append({
                        'start_time': voice_start_time,
                        'current_time': current_time,
                        'duration': current_time - voice_start_time,
                        'dominant_emotion': voice_emotion['dominant_emotion'],
                        'confidence': voice_emotion['confidence']
                    })
                    print(f"📢 Stored voice segment in progress: {voice_emotion['dominant_emotion']}")
                
                # Save the current data before managing size
                save_to_excel(emotion_df, excel_filename)
                
                # Apply the rolling buffer instead of clearing
                emotion_df = manage_data_size(emotion_df, max_rows=max_rows, buffer_seconds=buffer_seconds)
            
            last_manage_time = current_time
        
        # Stop recording automatically after 10 seconds
        if recording and (current_time - start_time >= recording_duration):
            recording = False
            print("⏹️ Recording stopped automatically after 10 seconds.")
            analyze_emotions(emotion_history)

        # Process detected faces - but only log at the specified interval
        should_log = (current_time - last_log_time) >= logging_interval
        
        if faces is not None and len(faces) > 0:
            for face in faces:
                x, y, w, h = map(int, face[:4])
                face_roi = rgb_frame[y:y+h, x:x+w]
                try:
                    result = DeepFace.analyze(face_roi, actions=['emotion'], enforce_detection=False)
                    if result:
                        emotions = result[0]['emotion']
                        
                        # Boosted emotion recognition for non-neutral emotions
                        boost_factor = {
                            "sad": 2.0,
                            "happy": 2.0,
                            "surprise": 1.5,
                            "angry": 1.5,
                            "disgust": 1.5,
                            "fear": 1.5,
                            "neutral": 1.0
                        }
                        
                        # Apply boost factors to all emotions except neutral
                        updated_emotions = {}
                        for emotion, score in emotions.items():
                            if emotion == "neutral":
                                updated_emotions[emotion] = score * 0.75  # Reduce neutral scores by 25%
                            else:
                                updated_emotions[emotion] = score * boost_factor.get(emotion, 1.0)
                        
                        dominant_emotion = max(updated_emotions, key=updated_emotions.get)
                        confidence = updated_emotions[dominant_emotion]
                        
                        # Store in emotion history if actively recording
                        if recording:
                            emotion_history.append({
                                'timestamp': current_time - start_time,
                                'emotion': dominant_emotion,
                                'confidence': confidence,
                                'all_emotions': updated_emotions
                            })
                        
                        # Continuous logging to DataFrame at specified interval
                        if continuous_logging and should_log:
                            datetime_str = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                            new_row = {
                                'timestamp': current_time,
                                'datetime': datetime_str,
                                'dominant_emotion': dominant_emotion,
                                'confidence': confidence
                            }
                            # Add individual emotion scores
                            for emotion in all_emotions:
                                new_row[f"{emotion}_score"] = updated_emotions.get(emotion, 0)
                            
                            emotion_df = pd.concat([emotion_df, pd.DataFrame([new_row])], ignore_index=True)
                            last_log_time = current_time  # Reset log timer
                        
                        # Display current emotion with confidence score
                        emotion_text = f"{dominant_emotion}: {confidence:.1f}"
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        cv2.putText(frame, emotion_text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        # Show top 3 emotions in the corner of the screen (helpful for debugging)
                        sorted_emotions = sorted(updated_emotions.items(), key=lambda x: x[1], reverse=True)[:3]
                        for i, (emotion, score) in enumerate(sorted_emotions):
                            cv2.putText(frame, f"{emotion}: {score:.1f}", (10, 60 + i*25), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                            
                except Exception as e:
                    print(f"⚠️ Error analyzing emotion: {e}")

        # Save to Excel periodically
        if time.time() - last_save_time > save_interval and not emotion_df.empty:
            save_to_excel(emotion_df, excel_filename)
            last_save_time = time.time()

        # Display recording status and timer
        if recording:
            elapsed = current_time - start_time
            remaining = max(0, recording_duration - elapsed)
            status_text = f"Recording: {remaining:.1f}s left"
            cv2.putText(frame, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        elif continuous_logging:
            rows_logged = len(emotion_df)
            next_manage = max(0, manage_interval - (current_time - last_manage_time))
            cv2.putText(frame, f"Logged: {rows_logged} rows | Manage in: {next_manage:.0f}s", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 128, 255), 2)
        
        # Display voice recording status if active
        if voice_recording:
            voice_elapsed = current_time - voice_start_time
            cv2.putText(frame, f"Voice Recording: {voice_elapsed:.1f}s", (10, height - 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # Add Pi connection indicator
        cv2.putText(frame, f"Pi: {PI_IP}", (width - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        cv2.imshow("Pi Camera - Emotion Detection", frame)
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('s'):
            recording = True
            emotion_history.clear()
            start_time = time.time()
            print("▶️ Started recording emotions for 10 seconds.")
        elif key == ord('e'):
            if recording:
                recording = False
                print("⏹️ Recording stopped manually.")
                analyze_emotions(emotion_history)
        elif key == ord('v'):
            # Toggle voice recording marker
            if not voice_recording:
                voice_recording = True
                voice_start_time = current_time
                print(f"🎤 Voice recording marker STARTED at timestamp {voice_start_time}")
            else:
                voice_recording = False
                voice_end_time = current_time
                voice_duration = voice_end_time - voice_start_time
                print(f"🎤 Voice recording marker STOPPED at timestamp {voice_end_time} (Duration: {voice_duration:.2f}s)")
                
                # Get dominant emotion for this voice clip
                if not emotion_df.empty:
                    voice_emotion = get_dominant_emotion_for_timerange(emotion_df, voice_start_time, voice_end_time)
                    voice_segments.append({
                        'start_time': voice_start_time,
                        'end_time': voice_end_time,
                        'duration': voice_duration,
                        'dominant_emotion': voice_emotion['dominant_emotion'],
                        'confidence': voice_emotion['confidence']
                    })
                    
                    print(f"\n🔍 Voice Segment Emotion Analysis:")
                    print(f"  Dominant emotion: {voice_emotion['dominant_emotion']} (confidence: {voice_emotion['confidence']:.2f})")
                    print(f"  Frames analyzed: {voice_emotion['frame_count']}")
                    print(f"  Duration: {voice_emotion['duration_seconds']:.2f}s")
                    print("\n  Emotion scores:")
                    for emotion, score in sorted(voice_emotion['emotion_scores'].items(), key=lambda x: x[1], reverse=True):
                        print(f"    {emotion}: {score:.2f}")
                    
                    # Save voice segments to a separate Excel file
                    voice_segments_df = pd.DataFrame(voice_segments)
                    voice_segments_df.to_excel(f"{data_dir}/voice_segments.xlsx", index=False)
                    print(f"💾 Voice segments saved to {data_dir}/voice_segments.xlsx")
        elif key == ord('c'):
            # Clear the DataFrame and start fresh
            emotion_df = pd.DataFrame(columns=columns)
            print("🗑️ Emotion data cleared.")
        elif key == ord('a'):
            # Create a summary Excel with different time periods
            if not emotion_df.empty:
                create_summary_excel(emotion_df, summary_filename, period_seconds=1)
        elif key == ord('r'):
            # Reconnect to Raspberry Pi
            print("🔄 Reconnecting to Raspberry Pi...")
            camera_client.close()
            if not camera_client.connect():
                print("❌ Reconnection failed")
        elif key == ord('q'):
            # Save final data before exiting
            if not emotion_df.empty:
                save_to_excel(emotion_df, excel_filename)   
                # Also create a summary before exiting
                create_summary_excel(emotion_df, summary_filename, period_seconds=1)
            break

except KeyboardInterrupt:
    print("\n🛑 Stopped by user (Ctrl+C)")
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
finally:
    # Clean up
    camera_client.close()
    cv2.destroyAllWindows()
    print(f"\n✅ Session ended. All emotion data saved to {excel_filename}")
    if voice_segments:
        print(f"🎤 Voice segments saved to {data_dir}/voice_segments.xlsx")