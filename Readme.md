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
│   │   ├── server.js
│   │   └── package.json
│   ├── profileService/
│   │   ├── Dockerfile
│   │   ├── .env
│   │   ├── server.js
│   │   └── package.json
├── frontend/
│   ├── Dockerfile
│   ├── .env
│   ├── src/
│   └── package.json
├── Screenshots/
│   ├── login-ecr.png
├── .dockerignore
├── .gitignore
└── README.md
```

---

## 🔐 Environment Variables

Each service uses `.env` files (excluded from Git) for configuration:

### `backend/profileService/.env`
```env
PORT=3002
MONGO_URL=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/profileDB?retryWrites=true&w=majority
NODE_ENV=production
```

### `backend/helloService/.env`
```env
PORT=3001
NODE_ENV=production
```

### `frontend/.env`
```env
REACT_APP_API_URL=http://localhost:3001
REACT_APP_PROFILE_API_URL=http://localhost:3002
```

---

## 🐳 Docker Configuration

Each service was containerized using optimized `Dockerfile` configurations.

### Build Commands

```bash
# Build helloService
cd backend/helloService
docker build -t hello-service .

# Build profileService  
cd ../profileService
docker build -t profile-service .

# Build frontend
cd ../../frontend
docker build -t frontend-app .
```

### Local Testing
```bash
# Test individual services (run each in separate terminals)
docker run -p 3001:3001 --env-file backend/helloService/.env hello-service
docker run -p 3002:3002 --env-file backend/profileService/.env profile-service  
docker run -p 3000:3000 --env-file frontend/.env frontend-app

# Or test services without Docker (Node.js directly)
cd backend/helloService && npm start
cd backend/profileService && npm start
cd frontend && npm start
```

---

## 🐳 Docker Images Pushed to ECR

**AWS Configuration:**
- **Region:** `ap-south-1` (Mumbai)
- **Account ID:** `975050024946`
- **ECR Repository:** `prince-reg`

### ECR Authentication

```bash
aws ecr get-login-password --region ap-south-1 \
| docker login --username AWS --password-stdin 975050024946.dkr.ecr.ap-south-1.amazonaws.com
```

### Tag Images for ECR

```bash
docker tag hello-service:latest 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:hello-service
docker tag profile-service:latest 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:profile-service
docker tag frontend-app:latest 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:frontend
```

### Push Images to ECR

```bash
docker push 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:hello-service
docker push 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:profile-service
docker push 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:frontend
```

✅ **Status:** All image tags are successfully pushed to the `prince-reg` ECR repository.

---

## 🚀 Deployment Architecture

### Current Phase: Docker + ECR ✅
- [x] Microservices containerized with Docker
- [x] Images built and tested locally
- [x] Images pushed to Amazon ECR
- [x] ECR repository configured with proper permissions

### Next Phase: CI/CD Pipeline
- [ ] Push code to AWS CodeCommit
- [ ] Configure Jenkins for automated builds
- [ ] Set up CI/CD pipeline from CodeCommit to ECR
- [ ] Implement automated testing in pipeline

### Next Phase: AWS Deployment
- [ ] Deploy backend services with Auto Scaling Groups
- [ ] Configure Application Load Balancer
- [ ] Deploy frontend on EC2 instances
- [ ] Set up RDS for production database

### Next Phase: Kubernetes Orchestration
- [ ] Deploy to Amazon EKS cluster
- [ ] Configure Helm charts for services
- [ ] Set up ingress controllers
- [ ] Implement service mesh (optional)

### Next Phase: Monitoring & Backup
- [ ] CloudWatch monitoring and alerting
- [ ] Lambda functions for automated backups
- [ ] S3 integration for data persistence
- [ ] Cost optimization and scaling policies

---

## 🔧 Technical Specifications

### Image Details
| Service | Base Image | Size | Layers |
|---------|------------|------|---------|
| Hello Service | `node:18-alpine` | ~150MB | 8 |
| Profile Service | `node:18-alpine` | ~165MB | 9 |
| Frontend | `node:18-alpine` | ~200MB | 10 |

### Security Features
- Multi-stage Docker builds for smaller images
- Non-root user execution in containers
- Environment variables for sensitive data
- Individual .dockerignore files for each service
- No docker-compose used - manual container orchestration for better control

---

## 📋 Prerequisites

### Required Software
- Docker Desktop or Docker Engine
- AWS CLI v2
- Node.js 18+ (for local development)
- Git

### AWS Permissions Required
- ECR: `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage`, `ecr:PutImage`
- IAM: Appropriate policies for ECR access

---

## 🐛 Troubleshooting

### Common Issues

**ECR Login Fails:**
```bash
# Ensure AWS CLI is configured
aws configure list

# Check ECR permissions
aws ecr describe-repositories --region ap-south-1
```

**Docker Build Fails:**
```bash
# Check Docker daemon
docker info

# Clear Docker cache
docker system prune -a
```

**Image Push Timeout:**
```bash
# Check network connectivity
ping 975050024946.dkr.ecr.ap-south-1.amazonaws.com

# Retry with verbose output
docker push --disable-content-trust 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:hello-service
```

---

## 📝 Development Notes

- MongoDB Atlas is used for the database (connection string in `.env`)
- Each service includes health check endpoints
- CORS is configured for cross-origin requests
- Environment-specific configurations are managed through `.env` files
- Docker images are optimized for production deployment
- **No docker-compose used** - services are built and run individually for maximum flexibility
- Each service has its own `.dockerignore` file for optimized builds
- Screenshots documented in `/Screenshots` folder for project reference

---

## 🎯 Success Metrics

- ✅ All services successfully containerized
- ✅ Images built without errors
- ✅ ECR repository configured and accessible
- ✅ All images pushed to ECR successfully
- ✅ Ready for next phase deployment

---

**🛠 Maintained by:** Prince Thakur  
**🎓 Submission for:** Hero Vired Graded Project – Orchestration and Scaling  
**📅 Last Updated:** $(date)  
**🔗 ECR Repository:** [prince-reg](https://ap-south-1.console.aws.amazon.com/ecr/repositories/prince-reg)

---

### 📞 Support
For issues or questions regarding this project, please contact the maintainer or refer to the project documentation.