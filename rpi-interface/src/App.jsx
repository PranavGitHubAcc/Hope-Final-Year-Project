import { useState, useRef, useEffect } from 'react';

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState('');
  const [audioChunks, setAudioChunks] = useState([]);
  const mediaRecorder = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => {
    return () => {
      // Cleanup function to stop any ongoing recordings when component unmounts
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 44100
        } 
      });
      
      streamRef.current = stream;
      const options = { mimeType: 'audio/webm;codecs=opus' };
      const mediaRecorderInstance = new MediaRecorder(stream, options);
      mediaRecorder.current = mediaRecorderInstance;
      
      // Reset audio chunks
      setAudioChunks([]);

      // Collect data every 100ms for better performance
      mediaRecorderInstance.ondataavailable = (event) => {
        if (event.data.size > 0) {
          setAudioChunks(prev => [...prev, event.data]);
        }
      };

      // Start recording with timeslice to get regular data updates
      mediaRecorderInstance.start(100);
      setIsRecording(true);
    } catch (err) {
      console.error('Error accessing microphone:', err);
      alert('Could not access microphone. Please ensure you have granted microphone permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorder.current && mediaRecorder.current.state !== 'inactive') {
      // Request final data
      mediaRecorder.current.requestData();
      mediaRecorder.current.stop();
      
      mediaRecorder.current.onstop = () => {
        // Create a blob with the correct MIME type
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        const audioUrl = URL.createObjectURL(audioBlob);
        
        // Update state with the audio URL
        setAudioUrl(audioUrl);
        setIsRecording(false);
        
        // Stop all tracks in the stream
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(track => {
            track.stop();
          });
          streamRef.current = null;
        }
      };
    }
  };

  const downloadAudio = () => {
    if (!audioUrl) return;
    
    const a = document.createElement('a');
    a.href = audioUrl;
    a.download = 'recording.wav';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-lg p-6 space-y-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-800 mb-2">Voice Recorder</h1>
          <p className="text-gray-600">Record and download your voice notes</p>
        </div>

        <div className="flex justify-center">
          {!isRecording ? (
            <button
              onClick={startRecording}
              className="flex items-center justify-center w-16 h-16 rounded-full bg-red-500 hover:bg-red-600 text-white shadow-lg transform hover:scale-105 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-opacity-50"
              aria-label="Start recording"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </button>
          ) : (
            <div className="flex flex-col items-center space-y-4">
              <div className="relative">
                <div className="absolute inset-0 bg-red-400 rounded-full opacity-75 animate-ping"></div>
                <button
                  onClick={stopRecording}
                  className="relative flex items-center justify-center w-16 h-16 rounded-full bg-red-600 hover:bg-red-700 text-white shadow-lg transform hover:scale-105 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-opacity-50"
                  aria-label="Stop recording"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
                  </svg>
                </button>
              </div>
              <span className="text-sm font-medium text-red-600 animate-pulse">Recording...</span>
            </div>
          )}
        </div>

        {audioUrl && (
          <div className="mt-6 space-y-4">
            <h3 className="text-lg font-medium text-gray-800">Your Recording</h3>
            <div className="bg-gray-50 p-4 rounded-lg">
                <audio 
                  controls 
                  src={audioUrl} 
                  className="w-full"
                  key={audioUrl} // Force re-render when URL changes
                />
            </div>
            <button
              onClick={downloadAudio}
              className="w-full flex items-center justify-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors duration-200"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download Recording
            </button>
          </div>
        )}

        <div className="text-center text-xs text-gray-500 mt-6">
          <p>Click the microphone to start recording</p>
          {isRecording && <p className="text-red-500 mt-1">Recording in progress...</p>}
        </div>
      </div>
    </div>
  );
}

export default App;