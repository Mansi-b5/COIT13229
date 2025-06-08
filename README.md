# Distributed Multiplayer Towers of Hanoi 🗼🌐

This project is a **distributed system** implementation of the classic *Towers of Hanoi* puzzle, designed to support **multiplayer interaction**, **real-time updates**, and **fault tolerance** across two scenarios:

- A **centralized client-server model** for internal organizational use (e.g. LAN/VPN).
- A **decentralized cloud-based model** for global internet users (designed to scale up to a billion users).

> 🎥 [Watch the project demo & explanation on YouTube](https://youtu.be/YBz9jEeUdVI)

---
## 🚀 Features

- Multiplayer Towers of Hanoi gameplay
- Real-time game state synchronization
- Chat system between users
- Session recovery after disconnects
- Centralized and cloud-based deployment options
- Fault-tolerant design with ZooKeeper and ZeroMQ
- Matchmaking (Scenario 2) based on region or skill level
