import os
import sqlite3
import time
import hmac
import hashlib
import json
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

NODE_ID = os.getenv("NODE_ID", "Alpha")
PORT = int(os.getenv("PORT", 8000))
DB_PATH = os.getenv("DB_PATH", "ledger.db")
SHARED_SECRET = os.getenv("SHARED_SECRET", "default-secret")

app = FastAPI(title=f"Sovereign Node {NODE_ID}")

class ThermodynamicGovernor:
    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold

    def evaluate(self, tool: str, entropy: float) -> dict:
        if entropy > 0.90:
            return {"status": "HALT", "penalty": 0, "mult": 0.0}
        elif entropy > self.threshold:
            penalty = int(50 * (entropy / self.threshold))
            return {"status": "HIGH_ENTROPY_PENALTY", "penalty": penalty, "mult": 0.5}
        return {"status": "OPTIMAL", "penalty": 0, "mult": 1.0}

class AgentWallet:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL, agent_id TEXT, amount_sats INTEGER, status TEXT
                )
            """)

    def log(self, agent_id: str, amount: int, status: str):
        with self.conn:
            self.conn.execute("INSERT INTO ledger (timestamp, agent_id, amount_sats, status) VALUES (?, ?, ?, ?)", 
                              (time.time(), agent_id, amount, status))

    def balance(self, agent_id: str) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT SUM(amount_sats) FROM ledger WHERE agent_id = ?", (agent_id,))
        res = cur.fetchone()[0]
        return res if res else 0

class CryptoSigner:
    def __init__(self, secret: str):
        self.key = secret.encode('utf-8')

    def sign(self, data: dict) -> str:
        b = json.dumps(data, sort_keys=True).encode('utf-8')
        return hmac.new(self.key, b, hashlib.sha256).hexdigest()

governor = ThermodynamicGovernor()
wallet = AgentWallet(DB_PATH)
signer = CryptoSigner(SHARED_SECRET)

class Task(BaseModel):
    agent_id: str
    tool_name: str
    query: str
    entropy_score: float

@app.post("/execute")
def execute(task: Task):
    ev = governor.evaluate(task.tool_name, task.entropy_score)
    if ev["status"] == "HALT":
        wallet.log(task.agent_id, 0, "HALT_RUNAWAY")
        raise HTTPException(status_code=403, detail="Halted by Governor")
    
    cost = int(100 * ev["mult"] + ev["penalty"])
    wallet.log(task.agent_id, -cost, ev["status"])
    
    metrics = {"agent_id": task.agent_id, "tool_name": task.tool_name, "status": ev["status"], "entropy": task.entropy_score, "cost": cost}
    proof = signer.sign(metrics)
    metrics["proof"] = proof
    
    return {"node": NODE_ID, "status": "success", "metrics": metrics, "balance": wallet.balance(task.agent_id)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
