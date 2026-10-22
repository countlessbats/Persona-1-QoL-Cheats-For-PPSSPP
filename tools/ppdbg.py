"""Small synchronous client for PPSSPP's WebSocket debugger, for reverse engineering."""
import base64, json, subprocess, re
from websockets.sync.client import connect


def find_port(pid=None):
    out = subprocess.run(['netstat', '-ano'], capture_output=True, text=True).stdout
    if pid is None:
        tasks = subprocess.run(['tasklist', '/fo', 'csv', '/nh'], capture_output=True, text=True).stdout
        pids = [l.split('","')[1] for l in tasks.splitlines() if 'PPSSPPWindows' in l]
        if not pids:
            raise SystemExit('PPSSPP is not running')
        pid = pids[0]
    for line in out.splitlines():
        m = re.match(r'\s*TCP\s+(?:0\.0\.0\.0|127\.0\.0\.1):(\d+)\s+\S+\s+LISTENING\s+(\d+)', line)
        if m and m.group(2) == str(pid):
            return int(m.group(1))
    raise SystemExit('PPSSPP debugger is not listening')


class Debugger:
    def __init__(self, port=None):
        self.ws = connect(f'ws://127.0.0.1:{port or find_port()}/debugger', max_size=None, open_timeout=5)
        self.n = 0
        self.events = []  # unsolicited events (log lines, breakpoint hits) seen while waiting

    def call(self, event, **params):
        self.n += 1
        ticket = str(self.n)
        self.ws.send(json.dumps({'event': event, 'ticket': ticket, **params}))
        while True:
            msg = json.loads(self.ws.recv(timeout=10))
            if msg.get('ticket') == ticket:
                if msg.get('event') == 'error':
                    raise RuntimeError(msg.get('message'))
                return msg
            self.events.append(msg)

    def send(self, event, **params):
        """Fire and forget; any reply lands in poll()."""
        self.ws.send(json.dumps({'event': event, **params}))

    def poll(self, timeout=0.1):
        try:
            return json.loads(self.ws.recv(timeout=timeout))
        except TimeoutError:
            return None

    def read(self, address, size):
        return base64.b64decode(self.call('memory.read', address=address, size=size)['base64'])

    def screenshot(self, path):
        """Pause briefly, save the displayed frame as PNG, resume."""
        was = self.call('cpu.status').get('stepping')
        if not was:
            # cpu.stepping answers with an untagged event, so send it raw and wait for the state.
            self.ws.send(json.dumps({'event': 'cpu.stepping'}))
            while not self.call('cpu.status').get('stepping'):
                pass
        try:
            r = self.call('gpu.buffer.screenshot', type='uri')
            open(path, 'wb').write(base64.b64decode(r['uri'].split(',', 1)[1]))
        finally:
            if not was:
                self.resume()

    def resume(self):
        self.ws.send(json.dumps({'event': 'cpu.resume'}))
        while self.call('cpu.status').get('stepping'):
            pass

    def pause(self):
        self.ws.send(json.dumps({'event': 'cpu.stepping'}))
        while not self.call('cpu.status').get('stepping'):
            pass

    def u32(self, address):
        return int.from_bytes(self.read(address, 4), 'little')
