# Cloud-Project-Part-2: P2P "StringChain" Network

This repository demonstrates a minimal peer-to-peer network where one node type ("BC") exposes a simple on-chain string storage contract, running on a local Hardhat node. Other node types (ML, IoT) are included as examples but are outside the scope of the blockchain setup.

---

## Prerequisites

1. **Node.js ≥ 18** (use [nvm](https://github.com/nvm-sh/nvm) if desired)
2. **npm** (comes with Node.js)
3. **Python ≥ 3.10** (use [pyenv](https://github.com/pyenv/pyenv) or system install)
4. **Git**

---

## Installation & Setup

### 1. Clone & Enter Repo

```bash
git https://github.com/ZhaozhongLiu/Cloud-Project-Part-2.git
cd Cloud-Project-Part-2
```

### 2. Install Node Dependencies

```bash
npm ci
```

Installs Hardhat and its plugins for contract compilation & deployment.

### 3. Prepare Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

This pulls in `web3`, `python-dotenv`, and any other handlers’ dependencies.

### 4. Create and Edit `.env`

```bash
cp .env.example .env
```

Open `.env` and set:

```
RPC_URL=http://127.0.0.1:8545
CHAIN_ID=31337
PRIVATE_KEY=<paste Hardhat Account #0 private key here>
```

---

## Blockchain Setup

### 5. Start Local Hardhat Node

In terminal A:

```bash
npx hardhat node
```

You should see:

```
Started HTTP JSON-RPC server at http://127.0.0.1:8545/
Accounts:
  Account #0: 0x... (10000 ETH)  Private Key: 0x...
  ...
```

### 6. Compile & Deploy Contract

In terminal B (same directory):

```bash
npx hardhat run --network localhost scripts/deploy.js
```

* Compiles `contracts/StringChain.sol`
* Deploys to your local chain
* Writes deployed address to `stringchain.addr`

Confirm by:

```bash
cat stringchain.addr
# e.g. 0x5FbDB2315678afecb367f032d93f642f64180aa3
```

---

## Running BC Nodes

### 7. Launch Peer Processes

Open two new terminals for Node A and Node B:

```bash
# Node A
source .venv/bin/activate
python3 peer.py 8000 5 BC

# Node B
source .venv/bin/activate
python3 peer.py 8001 5 BC
```

Each will print a simple CLI prompt.

### 8. Register Peers

On **Node A** prompt:

```text
cmd> add bc1 127.0.0.1 8001 BC
```

On **Node B** prompt:

```text
cmd> add bc0 127.0.0.1 8000 BC
```

### 9. Store & Fetch Data

On **Node A**:

```text
cmd> bc_store "Hello from A"
✓ Data written to chain
```

On **Node B**:

```text
cmd> bc_fetch
→ On-chain data: ['Hello from A']
```

> If you only start **one** BC node, you can still run `bc_store` and `bc_fetch` without the `add` step.



## Project Structure

```
.
├── contracts/
│   └── StringChain.sol
├── scripts/
│   └── deploy.js
├── handlers/
│   ├── bc_handlers.py
│   ├── ml_handlers.py
│   └── iot_handlers.py
├── peer.py
├── btpeer.py
├── requirements.txt
├── package.json
├── hardhat.config.js
├── stringchain.addr
└── README.md
```


