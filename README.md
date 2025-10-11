# 💧 Aquajal - Water Supply Management System

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-Framework-green.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status](https://img.shields.io/badge/Status-Active-success.svg)

**Aquajal** is a comprehensive web application designed to manage a **water jar supply business**.  
It provides a **multi-user environment** with distinct roles for administrators, managers, staff, and customers — streamlining daily operations from delivery logging to stock management.

---

## 📚 Table of Contents
- [Key Features](#-key-features)
- [Deployment on Synology NAS with Docker](#-deployment-on-synology-nas-with-docker)
  - [Prerequisites](#-prerequisites)
  - [Step 1: Prepare the Project on Your NAS](#-step-1-prepare-the-project-on-your-nas)
  - [Step 2: Create a Persistent Data Directory](#-step-2-create-a-persistent-data-directory)
  - [Step 3: Build and Run the Docker Container](#-step-3-build-and-run-the-docker-container)
  - [Step 4: Access Your Application](#-step-4-access-your-application)
- [Default Login Credentials](#-default-login-credentials)
- [Local Development Setup (Without Docker)](#-local-development-setup-without-docker)
- [Screenshots](#-screenshots)
- [Author](#-author)
- [License](#-license)

---

## 🚀 Key Features

### 🔐 Role-Based Access Control
- **Admin:** Manages businesses, users, and system settings.  
- **Manager:** Oversees staff, manages customers, handles stock, confirms event bookings, and views reports.  
- **Staff (Delivery):** Logs daily jar deliveries, records expenses, and manages cash balance.  
- **Customer:** Views delivery history, requests jars, and books jars for events.

### 🏢 Business Management
- Supports **multiple business locations or plants**, each with its own staff, customers, and pricing.

### 📦 Customer & Delivery Logging
- Staff can easily find customers and log daily deliveries.  
- Automatically calculates the collected amount per delivery.

### 🧾 Stock Management
- Managers can track and update the inventory of water jars and dispensers.

### 💰 Expense Tracking
- Delivery staff can record daily expenses (like fuel), deducted from their cash balance.

### ⚙️ Automated Wage Calculation
- Scheduled job automatically calculates and deducts daily wages based on delivery performance.

### 🌐 Customer Portal
- Customers have a dedicated dashboard to manage requests and event bookings.

---

## 🐳 Deployment on Synology NAS with Docker

This guide will help you deploy **Aquajal** on your **Synology NAS** using **Docker**.

---

### 📋 Prerequisites

- **Synology NAS:** A model that supports Docker  
- **Docker Package:** Installed from Synology’s *Package Center*  
- **Project Files:** Includes `Dockerfile`, `docker-compose.yml`, and `requirements.txt`

---

### ⚙️ Step 1: Prepare the Project on Your NAS

1. Open **File Station** on your Synology NAS.  
2. Create a new shared folder named `docker`.  
3. Inside it, create a subfolder named `aquajal`.  
4. Upload all project files into `docker/aquajal/`.

---

### 📁 Step 2: Create a Persistent Data Directory

1. Inside `docker/aquajal`, create a new folder named `data`.  
   - This folder will store the **SQLite database** and user uploads.  
2. The existing `docker-compose.yml` is already configured to use this directory.

---

### 🧱 Step 3: Build and Run the Docker Container

#### Enable SSH on your NAS
- Go to **Control Panel → Terminal & SNMP**  
- Check **Enable SSH service** → Click **Apply**

#### Connect via SSH
```bash
ssh your_nas_username@your_nas_ip_address
Navigate to the project directory
bash
Copy code
cd /volume1/docker/aquajal
Build and start the container
bash
Copy code
sudo docker-compose up --build -d
Check container logs
bash
Copy code
sudo docker-compose logs -f
You should see the Gunicorn server starting.
Press Ctrl + C to exit logs.

🌍 Step 4: Access Your Application
Once running, open your browser and visit:
👉 http://your_nas_ip_address:2942

You should see the Aquajal login page.

🔑 Default Login Credentials
After deployment, seed the database to create default users.

Connect to your NAS again
bash
Copy code
cd /volume1/docker/aquajal
Run the seed command
bash
Copy code
sudo docker-compose exec web flask seed-db
Role	Username	Password
Admin	admin	adminpass
Manager	manager	managerpass
Staff	staff	staffpass

💻 Local Development Setup (Without Docker)
Clone the repository
bash
Copy code
git clone <your-repository-url>
cd aquajal-app
Create a virtual environment
bash
Copy code
python3 -m venv venv
source venv/bin/activate
Install dependencies
bash
Copy code
pip install -r requirements.txt
Initialize the database
bash
Copy code
flask db upgrade
Seed the database (optional)
bash
Copy code
flask seed-db
Run the application
bash
Copy code
flask run
Your app will be available at 👉 http://127.0.0.1:5000

🖼️ Screenshots
(Add screenshots of your UI here for better visualization)

Example structure:

bash
Copy code
/screenshots
 ├── login_page.png
 ├── dashboard.png
 ├── delivery_logs.png
 └── customer_portal.png
You can include images like:

markdown
Copy code
![Login Page](screenshots/login_page.png)
![Dashboard](screenshots/dashboard.png)
👨‍💻 Author
Rajat Poddar
💼 Developer & Maintainer of Aquajal
📧 Contact Me
🌐 GitHub Profile

📄 License
This project is licensed under the MIT License — see the LICENSE file for details.

