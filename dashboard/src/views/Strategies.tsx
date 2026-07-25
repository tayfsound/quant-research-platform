function Strategies() {
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Strategy Explorer</h2>
      <div className="bg-gray-900 rounded-lg p-4">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="p-2">Name</th><th className="p-2">Generation</th><th className="p-2">Sharpe</th><th className="p-2">Return</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-gray-800">
              <td className="p-2">AlphaGen-42</td><td className="p-2">12</td><td className="p-2 text-green-400">2.31</td><td className="p-2 text-green-400">+34%</td>
            </tr>
            <tr className="border-b border-gray-800">
              <td className="p-2">BetaV-7</td><td className="p-2">5</td><td className="p-2">1.12</td><td className="p-2">+12%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
export default Strategies;
