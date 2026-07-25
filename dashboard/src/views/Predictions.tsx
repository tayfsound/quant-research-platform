function Predictions() {
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">AI Predictions</h2>
      <div className="grid grid-cols-3 gap-4">
        {['Trend', 'Momentum', 'Sentiment'].map(agent => (
          <div key={agent} className="bg-gray-900 rounded-lg p-4 border border-gray-800">
            <h3 className="text-lg font-semibold">{agent} Agent</h3>
            <p className="text-green-400 text-xl mt-2">LONG 82%</p>
            <p className="text-sm text-gray-500 mt-1">Confidence: High</p>
          </div>
        ))}
      </div>
    </div>
  );
}
export default Predictions;
