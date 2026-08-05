import { useEffect, useState } from 'react';

function LivePredictions() {
  const [prediction, setPrediction] = useState<any>(null);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/api/v1/stream/live');
    ws.onmessage = (event) => {
      setPrediction(JSON.parse(event.data));
    };
    return () => ws.close();
  }, []);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Live AI Predictions</h2>
      {prediction ? (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <div className="flex gap-8 items-center">
            <div>
              <span className="text-gray-400">Symbol:</span>
              <span className="text-xl ml-2">{prediction.symbol}</span>
            </div>
            <div>
              <span className="text-gray-400">Direction:</span>
              <span className={`text-xl ml-2 font-bold ${prediction.direction === 1 ? 'text-green-400' : prediction.direction === -1 ? 'text-red-400' : 'text-yellow-400'}`}>
                {prediction.direction === 1 ? 'LONG' : prediction.direction === -1 ? 'SHORT' : 'NEUTRAL'}
              </span>
            </div>
            <div>
              <span className="text-gray-400">Confidence:</span>
              <span className="text-xl ml-2">{(prediction.confidence * 100).toFixed(0)}%</span>
            </div>
          </div>
          <div className="mt-4 flex gap-4 text-sm text-gray-400">
            <span>RSI: {prediction.features.rsi}</span>
            <span>MACD: {prediction.features.macd}</span>
          </div>
        </div>
      ) : (
        <p className="text-gray-500">Connecting to live feed...</p>
      )}
    </div>
  );
}
export default LivePredictions;
