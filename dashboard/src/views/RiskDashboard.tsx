function RiskDashboard() {
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Risk Dashboard</h2>
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Daily Loss', value: '-$1,200', limit: '$5,000', status: 'ok' },
          { label: 'Drawdown', value: '4.2%', limit: '15%', status: 'ok' },
          { label: 'Exposure', value: '$45,000', limit: '$100,000', status: 'ok' },
          { label: 'Leverage', value: '2.5x', limit: '5x', status: 'ok' },
        ].map(item => (
          <div key={item.label} className="bg-gray-900 rounded-lg p-4 border border-gray-800">
            <p className="text-sm text-gray-400">{item.label}</p>
            <p className="text-xl font-bold">{item.value}</p>
            <p className="text-xs text-gray-500">Limit: {item.limit}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
export default RiskDashboard;
