pipeline {
    agent any
    
    parameters {
        choice(
            name: 'APP_TARGET',
            choices: [' ', 'frontend', 'hello-service', 'profile-service', 'build-all'],
            description: 'Select which app to build and push. Leave blank to auto-detect changed apps, or select "build-all" to build all services.'
        )
        choice(
            name: 'DEPLOY_TO_K8S',
            choices: ['false', 'true'],
            description: 'Deploy to Kubernetes after building images?'
        )
        choice(
            name: 'ENVIRONMENT',
            choices: ['development', 'staging', 'production'],
            description: 'Target environment for deployment'
        )
    }
    
    environment {
        AWS_REGION = 'ap-south-1'
        AWS_ACCOUNT_ID = '975050024946'
        ECR_REPOSITORY = 'prince-reg'
        CODE_REPO = 'https://github.com/XXRadeonXFX/AWS-Project-on-Orchestration-and-Scaling.git'
        CODE_BRANCH = 'main'
        TOPIC_ARN = 'arn:aws:sns:ap-south-1:975050024946:prince-topic'
        HELM_RELEASE_NAME = 'mern-app'
        NAMESPACE = 'default'
        EKS_CLUSTER_NAME = 'prince-ec2'
        MONGO_CONNECTION_STRING = 'mongodb+srv://radeonxfx:Password@cluster0.gdl7f.mongodb.net/SimpleMern'
    }
    
    stages {
        stage('Clone App Code') {
            steps {
                dir('app-code') {
                    git branch: "${env.CODE_BRANCH}", url: "${env.CODE_REPO}"
                    script {
                        def realCommit = sh(script: "git rev-parse HEAD", returnStdout: true).trim()
                        def shortCommit = realCommit.take(8)
                        echo "Cloned Commit: ${realCommit}"
                        echo "Short Commit: ${shortCommit}"
                        env.REPO_COMMIT = realCommit
                        env.SHORT_COMMIT = shortCommit
                        env.IMAGE_TAG = shortCommit
                        env.BUILD_NUMBER_TAG = "${env.BUILD_NUMBER}-${shortCommit}"
                    }
                }
            }
        }
        
        stage('Detect Changed Apps') {
            when {
                expression { return !params.APP_TARGET?.trim() }
            }
            steps {
                dir('app-code') {
                    script {
                        def changedFiles = sh(
                            script: "git diff-tree --no-commit-id --name-only -r ${env.REPO_COMMIT}",
                            returnStdout: true
                        ).trim().split("\n")
                        echo "Changed files: ${changedFiles}"
                        def targets = []
                        
                        if (changedFiles.any { it.startsWith("SampleMERNwithMicroservices/frontend/") }) {
                            targets << "frontend"
                        }
                        if (changedFiles.any { it.startsWith("SampleMERNwithMicroservices/backend/helloService/") }) {
                            targets << "hello-service"
                        }
                        if (changedFiles.any { it.startsWith("SampleMERNwithMicroservices/backend/profileService/") }) {
                            targets << "profile-service"
                        }
                        
                        if (targets) {
                            env.BUILD_TARGETS = targets.join(',')
                            echo "Auto-detected targets: ${env.BUILD_TARGETS}"
                        } else {
                            echo "No relevant app changes detected. Building all apps as fallback."
                            env.BUILD_TARGETS = "frontend,hello-service,profile-service"
                        }
                    }
                }
            }
        }
        
        stage('Set Build Targets') {
            when {
                expression { return params.APP_TARGET?.trim() }
            }
            steps {
                script {
                    if (params.APP_TARGET.trim() == 'build-all') {
                        env.BUILD_TARGETS = "frontend,hello-service,profile-service"
                        echo "Building all services: ${env.BUILD_TARGETS}"
                    } else {
                        env.BUILD_TARGETS = params.APP_TARGET.trim()
                        echo "Manual target selected: ${env.BUILD_TARGETS}"
                    }
                }
            }
        }
        
        stage('Login to ECR') {
            steps {
                withCredentials([[
                    $class: 'AmazonWebServicesCredentialsBinding',
                    credentialsId: 'PRINCE-AWS-CRED'
                ]]) {
                    sh """
                        echo 'Logging into AWS ECR...'
                        aws ecr get-login-password --region ${env.AWS_REGION} | \\
                        docker login --username AWS --password-stdin ${env.AWS_ACCOUNT_ID}.dkr.ecr.${env.AWS_REGION}.amazonaws.com
                    """
                }
            }
        }
        
        stage('Build & Push Docker Images') {
            steps {
                script {
                    if (!env.BUILD_TARGETS) {
                        error("No build targets available.")
                    }
                    def targets = env.BUILD_TARGETS.split(',')
                    echo "Building targets: ${targets}"
                    
                    for (app in targets) {
                        def dockerContext
                        def helmImageTag
                        
                        switch(app.trim()) {
                            case 'frontend':
                                dockerContext = 'SampleMERNwithMicroservices/frontend'
                                helmImageTag = 'fe-radeon'
                                break
                            case 'hello-service':
                                dockerContext = 'SampleMERNwithMicroservices/backend/helloService'
                                helmImageTag = 'hs-radeon'
                                break
                            case 'profile-service':
                                dockerContext = 'SampleMERNwithMicroservices/backend/profileService'
                                helmImageTag = 'ps-radeon'
                                break
                            default:
                                error "Unknown app target: ${app}"
                        }
                        
                        def ecr_uri = "${env.AWS_ACCOUNT_ID}.dkr.ecr.${env.AWS_REGION}.amazonaws.com/${env.ECR_REPOSITORY}"
                        def buildTag = "${env.BUILD_NUMBER_TAG}"
                        
                        echo "🔨 Building Docker image for ${app} from context: app-code/${dockerContext}"
                        
                        // Build the image
                        sh "docker build -t ${app}:${buildTag} app-code/${dockerContext}"
                        
                        // Tag for ECR (SIMPLIFIED - only 2 tags instead of 4)
                        echo "🏷️  Tagging image for ECR..."
                        sh """
                            docker tag ${app}:${buildTag} ${ecr_uri}:${helmImageTag}
                            docker tag ${app}:${buildTag} ${ecr_uri}:latest
                        """
                        
                        // Push to ECR (SIMPLIFIED - only 2 pushes instead of 4)
                        echo "🚀 Pushing images to ECR..."
                        sh """
                            docker push ${ecr_uri}:${helmImageTag}
                            docker push ${ecr_uri}:latest
                        """
                        
                        echo "✅ Successfully built and pushed ${app} to ${env.ECR_REPOSITORY} repository"
                        echo "   - Helm tag: ${helmImageTag}"
                        echo "   - Latest tag: latest"
                    }
                }
            }
        }
        
        stage('Deploy to Kubernetes') {
            when {
                expression { return params.DEPLOY_TO_K8S == 'true' }
            }
            steps {
                withCredentials([[
                    $class: 'AmazonWebServicesCredentialsBinding',
                    credentialsId: 'PRINCE-AWS-CRED'
                ]]) {
                    script {
                        echo "🚀 Deploying to Kubernetes environment: ${params.ENVIRONMENT}"
                        
                        // Update kubeconfig for EKS
                        sh """
                            aws eks update-kubeconfig --region ${env.AWS_REGION} --name ${env.EKS_CLUSTER_NAME}
                        """
                        
                        // Deploy using Helm
                        dir('app-code/SampleMERNwithMicroservices') {
                            sh """
                                # Deploy with Helm using environment variable
                                helm upgrade --install ${env.HELM_RELEASE_NAME} ./mern-microservices \\
                                    --namespace ${env.NAMESPACE} \\
                                    --create-namespace \\
                                    --set mongodb.connectionString="${env.MONGO_CONNECTION_STRING}" \\
                                    --set helloService.fullnameOverride="hello-service" \\
                                    --set profileService.fullnameOverride="profile-service" \\
                                    --set frontend.fullnameOverride="frontend" \\
                                    --set global.pullPolicy=Always \\
                                    --wait \\
                                    --timeout=10m
                            """
                        }
                        
                        // Verify deployment
                        sh """
                            echo "📊 Deployment Status:"
                            kubectl get pods -n ${env.NAMESPACE} -l app.kubernetes.io/instance=${env.HELM_RELEASE_NAME}
                            echo ""
                            kubectl get services -n ${env.NAMESPACE} -l app.kubernetes.io/instance=${env.HELM_RELEASE_NAME}
                        """
                    }
                }
            }
        }
        
        stage('Run Health Checks') {
            when {
                expression { return params.DEPLOY_TO_K8S == 'true' }
            }
            steps {
                script {
                    echo "🏥 Running health checks..."
                    sh """
                        # Wait for pods to be ready
                        kubectl wait --for=condition=ready pod -l app.kubernetes.io/instance=${env.HELM_RELEASE_NAME} -n ${env.NAMESPACE} --timeout=300s
                        
                        # Check service endpoints
                        kubectl get endpoints -n ${env.NAMESPACE} -l app.kubernetes.io/instance=${env.HELM_RELEASE_NAME}
                        
                        # Get external access information
                        echo ""
                        echo "🌐 External Access Information:"
                        kubectl get service frontend -n ${env.NAMESPACE} -o wide || echo "Frontend service not found"
                    """
                }
            }
        }
    }
    
    post {
        success {
            withCredentials([[
                $class: 'AmazonWebServicesCredentialsBinding',
                credentialsId: 'PRINCE-AWS-CRED'
            ]]) {
                script {
                    def deploymentStatus = params.DEPLOY_TO_K8S == 'true' ? "and deployed to ${params.ENVIRONMENT}" : "only"
                    sh """
                        aws sns publish \\
                          --region ${env.AWS_REGION} \\
                          --topic-arn "${env.TOPIC_ARN}" \\
                          --subject "✅ Jenkins Pipeline Success - Build ${env.BUILD_NUMBER}" \\
                          --message "Jenkins successfully built ${deploymentStatus} the following services: ${env.BUILD_TARGETS}
                        
📦 Build Details:
• Build Number: ${env.BUILD_NUMBER}
• Commit: ${env.SHORT_COMMIT}
• Environment: ${params.ENVIRONMENT}
• Targets: ${env.BUILD_TARGETS}
• ECR Repository: ${env.ECR_REPOSITORY}
• Timestamp: \$(date)

🔗 Images pushed with tags:
• Helm tags: fe-radeon, hs-radeon, ps-radeon
• Latest tag: latest (shared)

🚀 Deployment Status: ${params.DEPLOY_TO_K8S == 'true' ? 'Deployed to Kubernetes' : 'Build only - no deployment'}"
                    """
                }
            }
        }
        failure {
            withCredentials([[
                $class: 'AmazonWebServicesCredentialsBinding',
                credentialsId: 'PRINCE-AWS-CRED'
            ]]) {
                sh """
                    aws sns publish \\
                      --region ${env.AWS_REGION} \\
                      --topic-arn "${env.TOPIC_ARN}" \\
                      --subject "❌ Jenkins Pipeline Failed - Build ${env.BUILD_NUMBER}" \\
                      --message "Jenkins build failed for targets: ${env.BUILD_TARGETS}
                    
🚨 Failure Details:
• Build Number: ${env.BUILD_NUMBER}
• Commit: ${env.SHORT_COMMIT}
• Environment: ${params.ENVIRONMENT}
• Failed Stage: Check Jenkins logs
• Timestamp: \$(date)

Please check the Jenkins console output for detailed error information."
                """
            }
        }
        always {
            echo "🧹 Cleaning up Docker images..."
            sh """
                # Clean up local Docker images to save space
                docker system prune -f || true
            """
            echo "Pipeline completed. Build targets were: ${env.BUILD_TARGETS}"
        }
    }
}
