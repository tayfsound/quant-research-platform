const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws/cycle";

export class CycleWebSocket {
  private ws: WebSocket | null = null;
  private reconnectInterval = 5000;

  connect(onMessage: (data: any) => void) {
    this.ws = new WebSocket(WS_URL);
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      onMessage(data);
    };
    this.ws.onclose = () => {
      setTimeout(() => this.connect(onMessage), this.reconnectInterval);
    };
  }

  runCycle() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send("run_cycle");
    }
  }

  disconnect() {
    this.ws?.close();
  }
}
