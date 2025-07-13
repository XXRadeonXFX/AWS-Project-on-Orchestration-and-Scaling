Awesome! Since you’ve completed up to **pushing Docker images to Amazon ECR**, here's a complete and professional `README.md` you can copy-paste into your root directory (`SampleMERNwithMicroservices/README.md`) for submission so far.

---

## 📄 `README.md` (Up to Docker + ECR Phase)

```markdown
# Sample MERN with Microservices – Cloud Deployment (Graded Project)

This repository contains a MERN-based microservices application, deployed and orchestrated using AWS, Docker, and Amazon ECR. This document outlines the steps completed up to Docker image builds and pushing them to ECR.

---

## 📦 Microservices Overview

| Service Name     | Description                  | Port   |
|------------------|------------------------------|--------|
| `helloService`   | Basic test service           | 3001   |
| `profileService` | User profile with MongoDB    | 3002   |
| `frontend`       | React-based frontend app     | 3000   |

Each service is independently Dockerized and uses `.env` for configuration.

---

## 📁 Directory Structure

```

SampleMERNwithMicroservices/
├── backend/
│   ├── helloService/
│   │   ├── Dockerfile
│   │   ├── .env
│   ├── profileService/
│   │   ├── Dockerfile
│   │   ├── .env
├── frontend/
│   ├── Dockerfile
│   ├── .env
├── README.md

````

---

## 🔐 Environment Variables

Each service uses `.env` files (excluded from Git) for config:

### `backend/profileService/.env`
```env
PORT=3002
MONGO_URL=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/profileDB?retryWrites=true&w=majority
````

### `backend/helloService/.env`

```env
PORT=3001
```

### `frontend/.env`

```env
REACT_APP_API_URL=http://localhost:3001
```

---

## 🐳 Docker Image Build

Each service was containerized using a `Dockerfile`.

### Build Commands

```bash
# helloService
cd backend/helloService
docker build -t hello-service .

# profileService
cd ../profileService
docker build -t profile-service .

# frontend
cd ../../frontend
docker build -t frontend-app .
```

---

## 🐳 Docker Images Pushed to ECR

AWS Region: `ap-south-1 (Mumbai)`
AWS Account ID: `975050024946`
ECR Repository: `prince-reg`

### ECR Login

```bash
aws ecr get-login-password --region ap-south-1 \
| docker login --username AWS --password-stdin 975050024946.dkr.ecr.ap-south-1.amazonaws.com
```

### Tag Images

```bash
docker tag hello-service:latest 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:hello-service
docker tag profile-service:latest 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:profile-service
docker tag frontend-app:latest 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:frontend
```

### Push Images

```bash
docker push 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:hello-service
docker push 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:profile-service
docker push 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:frontend
```

✅ All image tags are now available in the `prince-reg` ECR repository.

---

## ✅ Next Steps (In Progress)

* [ ] Push code to AWS CodeCommit
* [ ] Jenkins job setup for CI/CD from CodeCommit
* [ ] Deploy backend with Auto Scaling + Load Balancer
* [ ] Deploy frontend on EC2
* [ ] Deploy to Amazon EKS with Helm
* [ ] Monitoring with CloudWatch
* [ ] Backup with Lambda + S3

---

## 📌 Notes

* `.env` files are excluded via `.dockerignore` and `.gitignore`
* MongoDB is hosted on MongoDB Atlas (URI provided in `.env`)
* Each image build was verified locally before ECR push

---

🛠 Maintained by: Prince Thakur
🎓 Submission for: Hero Vired Graded Project – Orchestration and Scaling

```

---

