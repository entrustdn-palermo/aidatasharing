# 🌱 Entrust Data Sharing MCP Platform

<div align="center">

**Agent-Based Data Sharing Protocol for Agricultural Sustainability Analysis**

*AI-Powered Multi-File Correlation with Persistent Context*

[![EU Horizon](https://img.shields.io/badge/EU%20Horizon-ENTRUST%20DN-blue?style=for-the-badge&logo=european-union)](https://entrustdn.eu)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)](https://www.python.org)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?style=for-the-badge&logo=next.js)](https://nextjs.org)
[![MindsDB](https://img.shields.io/badge/MindsDB-Agents-purple?style=for-the-badge)](https://mindsdb.com)

*Developed as part of the EU Horizon ENTRUST Doctoral Network*

*Università degli Studi di Palermo (UNIPA) | ELMI Software | Airfield Estate Dublin*

[🚀 Quick Start](#-quick-start) • [✨ Features](#-key-features) • [📖 Documentation](#-documentation) • [🤝 Contributing](#-contributing)

</div>

---

## 🎯 Project Overview

This platform was developed as part of the **EU Horizon ENTRUST Doctoral Network** (Marie Skłodowska-Curie Grant Agreement No 101073381) to address fundamental challenges in agricultural data analysis.

**Doctoral Candidate 01** | *This project has received funding from the European Union's Horizon 2021 research and innovation programme under the Marie Skłodowska-Curie grant agreement No 101073381*

Traditional AI systems analyze data files in isolation, leading to significant data underutilization. This platform introduces a **persistent agent-based architecture** that enables intelligent multi-file correlation and contextual analysis.

### 🏛️ Academic Context

- **Institution**: Università degli Studi di Palermo (UNIPA)
- **Academic Supervisors**: Biagio Lenzitti, Domenico Tegolo (UNIPA)
- **First Secondment**: ELMI Software, Palermo (Supervisors: Camillo Gioè, Vito Puleio)
- **Second Secondment**: Airfield Estate, Dublin, Ireland (September - November 2025)
- **Doctoral Candidate 01**: Nur Arifin Akbar

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- **MindsDB** (local or cloud instance)
- **Git**

### Installation

```bash
# Clone the repository
git clone https://github.com/entrustdn-palermo/aidatasharing.git
cd aidatasharing

# Run installation setup
python setup_fresh_install.py

# Start development environment
./start-dev.sh
```

### Access the Platform
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

### Default Credentials
- **Email**: admin@example.com
- **Password**: SuperAdmin123!

---

## ✨ Key Features

### 🧠 Agent-Based Architecture

**Persistent Context Memory**
- AI agents maintain understanding of data structure across sessions
- No need to re-explain data format with every query
- Accumulated domain-specific knowledge and patterns

**Multi-File Correlation**
- Analyze multiple related datasets simultaneously
- Cross-reference data across different sources
- Correlate information for comprehensive insights

**Adaptive Learning**
- Learns specific patterns of your data
- Contextual interpretation based on domain
- Handles real-world data characteristics (incomplete records, variations, seasonality)

**Performance Improvements**
- 60-75% faster response times through persistent context
- Optimized API usage (60% fewer calls)
- Non-blocking asynchronous processing

### 📊 Data Management

**Supported Formats**: CSV, XLSX, JSON, TXT, PDF, Parquet

**Key Capabilities**:
- Secure file upload and storage (S3-compatible)
- Automatic schema detection
- Multi-file dataset support
- PDF document analysis and extraction
- Data preview and exploration

### 🔐 Security & Collaboration

- JWT-based authentication
- Organization-scoped data isolation
- Secure sharing with time-limited tokens
- Comprehensive audit logging
- Role-based access control

---

## 🏗️ Architecture

### Technology Stack

**Backend**
- FastAPI (Modern async Python framework)
- SQLAlchemy ORM
- MindsDB SDK 3.4.8+
- AWS S3 / boto3 integration
- PostgreSQL / SQLite database

**Frontend**
- Next.js 15 with App Router
- React 18 with TypeScript
- Tailwind CSS
- Real-time updates

**AI Layer**
- MindsDB Agents (persistent context)
- GPT-4 via OpenAI
- Custom domain-specific prompts

### Agent-Based Processing Pipeline

```
User Upload → S3 Storage → Asynchronous Processing → MindsDB Agent Creation
                                                              ↓
User Query ← Intelligent Response ← Agent Analysis ← Persistent Context
```

---

## 📖 Documentation

### Complete Technical Report

A comprehensive technical report documents the implementation, testing, and validation:

**[📄 Read the Full Technical Report](report/COMPREHENSIVE_SECONDMENT_REPORT.md)**

**Report Contents**:
- Problem context and architectural necessity
- Design and implementation details
- Real-world testing and validation
- Technical insights and best practices
- Performance metrics and evidence

### Project Structure

```
aidatasharing/
├── backend/                # FastAPI backend
│   ├── app/
│   │   ├── api/           # REST API endpoints
│   │   ├── services/      # Business logic
│   │   ├── models/        # Database models
│   │   └── core/          # Configuration
│   └── tests/             # Test suite
│
├── frontend/              # Next.js frontend
│   ├── src/
│   │   ├── app/          # Pages
│   │   ├── components/   # React components
│   │   └── lib/          # Utilities
│   └── package.json
│
├── report/                # Technical documentation
├── storage/               # Data storage
├── .env                   # Configuration
└── README.md
```

---

## 🔧 Configuration

### Environment Variables

Configure via `.env` file or admin panel:

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/entrust_db

# MindsDB (Required)
MINDSDB_BASE_URL=http://localhost:47334
MINDSDB_AGENT_MODEL=gpt-4
USE_AGENT_BASED_CHAT=True

# File Processing
ALLOWED_FILE_TYPES=csv,xlsx,xls,json,txt,pdf,parquet
MAX_FILE_SIZE_MB=50

# S3 Storage
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
S3_BUCKET=entrust-datasets

# API Keys
OPENAI_API_KEY=your_openai_key
SECRET_KEY=your-secret-key
```

---

## 🧑‍💻 Development

### Setup Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
cd backend && pip install -r requirements.txt
cd ../frontend && npm install

# Start development servers
cd .. && ./start-dev.sh
```

### Development Commands

```bash
# Start full stack
./start-dev.sh

# Backend only
cd backend && uvicorn app.main:app --reload

# Frontend only
cd frontend && npm run dev

# Run tests
cd backend && pytest
```

---

## 🚀 Deployment

### Production Checklist

- [ ] Configure production environment variables
- [ ] Set up PostgreSQL database
- [ ] Configure S3 bucket with proper permissions
- [ ] Set up MindsDB production instance
- [ ] Configure reverse proxy (nginx/Caddy)
- [ ] Install SSL certificates
- [ ] Enable monitoring and logging

### Docker Deployment

```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f
```

---

## 🤝 Contributing

We welcome contributions from the research community!

### How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -m 'feat: add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Open a Pull Request

### Guidelines

- Follow PEP 8 for Python code
- Use TypeScript for frontend development
- Write tests for new features
- Update documentation
- Follow conventional commit messages

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2025 EU Horizon ENTRUST Doctoral Network
Marie Skłodowska-Curie Grant Agreement No 101073381
Università degli Studi di Palermo (UNIPA) | ELMI Software Palermo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software...
```

---

## 🙏 Acknowledgments

### 🇪🇺 EU Horizon ENTRUST Doctoral Network
- **Grant Agreement**: Marie Skłodowska-Curie No 101073381
- **Funding**: European Union's Horizon 2021 Research and Innovation Programme
- **Network**: Training experts in trustworthy AI for environmental sustainability
- **Position**: Doctoral Candidate 01

### 🏛️ Academic Supervision
- **Biagio Lenzitti** (UNIPA) - Academic supervision and guidance
- **Domenico Tegolo** (UNIPA) - Academic support

### 🏢 First Secondment - ELMI Software, Palermo
- **Camillo Gioè** - Secondment supervision
- **Vito Puleio** - Secondment support

### 🌾 Second Secondment - Airfield Estate, Dublin
- **Paul O'Keeffe** - Facilitation and support
- **Airfield Estate Team** - Collaboration and data access

### 💻 Open Source Community
- **MindsDB** - Agent-based AI framework
- **FastAPI** - Python web framework
- **Next.js** - React framework

---

## 📞 Contact & Support

### Getting Help

- 📧 **Email**: nurarifin.akbar@unipa.it
- 🐛 **Issues**: [GitHub Issues](https://github.com/entrustdn-palermo/aidatasharing/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/entrustdn-palermo/aidatasharing/discussions)
- 📚 **Documentation**: [Technical Report](report/COMPREHENSIVE_SECONDMENT_REPORT.md)
- 🌐 **Website**: [ENTRUST DN](https://entrustdn.eu)

### Research Collaboration

Interested in collaborating on agricultural AI research or agent-based data analysis? Contact us through UNIPA or the ENTRUST DN network.

---

<div align="center">

## ⭐ Star This Repository!

**If you find this project valuable, please star it on GitHub!**

Your support helps:
- 🎓 Increase visibility for agricultural AI research
- 🌍 Support the EU Horizon ENTRUST DN mission
- 🤝 Encourage open-source collaboration
- 📊 Demonstrate research impact

---

**Built with ❤️ for sustainable agriculture and trustworthy AI**

*EU Horizon ENTRUST Doctoral Network | UNIPA | ELMI Software | Airfield Estate*

[⬆ Back to Top](#-entrust-data-sharing-mcp-platform)

</div>
