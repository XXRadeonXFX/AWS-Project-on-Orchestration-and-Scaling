pipeline {
    agent any

    parameters {
        choice(
            name: 'APP_TARGET',
            choices: [' ', 'prince-mern-frontend', 'prince-mern-backend-helloservice'],
            description: 'Select which app to build and push. Leave blank to auto-detect changed apps.'
        )
    }

    environment {
        AWS_REGION = 'ap-south-1'
        AWS_ACCOUNT_ID = '975050024946'
        CODE_REPO = 'https://github.com/XXRadeonXFX/AWS-Project-on-Orchestration-and-Scaling.git'
        CODE_BRANCH = 'main'
        TOPIC_ARN = 'arn:aws:sns:ap-south-1:975050024946:prince-topic'
    }

    stages {
        stage('Clone App Code') {
            steps {
                dir('app-code') {
                    git branch: "${env.CODE_BRANCH}", url: "${env.CODE_REPO}"
                    script {
                        def realCommit = sh(script: "git rev-parse HEAD", returnStdout: true).trim()
                        echo "Cloned Commit: ${realCommit}"
                        env.REPO_COMMIT = realCommit
                        env.IMAGE_TAG = realCommit
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
                            targets << "prince-mern-frontend"
                        }
                        if (changedFiles.any { it.startsWith("SampleMERNwithMicroservices/backend/helloService/") }) {
                            targets << "prince-mern-backend-helloservice"
                        }

                        if (targets) {
                            env.BUILD_TARGETS = targets.join(',')
                            echo "Auto-detected targets: ${env.BUILD_TARGETS}"
                        } else {
                            echo "No relevant app changes detected. Building all apps as fallback."
                            env.BUILD_TARGETS = "prince-mern-frontend,prince-mern-backend-helloservice"
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
                    env.BUILD_TARGETS = params.APP_TARGET.trim()
                    echo "Manual target selected: ${env.BUILD_TARGETS}"
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
                        aws ecr get-login-password --region ${env.AWS_REGION} | \
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
                        // Map parameter names to internal names and Docker contexts
                        def dockerContext
                        def imageTag
                        
                        switch(app) {
                            case 'prince-mern-frontend':
                                dockerContext = 'SampleMERNwithMicroservices/frontend'
                                imageTag = 'frontend'
                                break
                            case 'prince-mern-backend-helloservice':
                                dockerContext = 'SampleMERNwithMicroservices/backend/helloService'
                                imageTag = 'hello-service'
                                break
                            case 'mern-frontend':
                                dockerContext = 'SampleMERNwithMicroservices/frontend'
                                imageTag = 'frontend'
                                break
                            case 'mern-backend-helloservice':
                                dockerContext = 'SampleMERNwithMicroservices/backend/helloService'
                                imageTag = 'hello-service'
                                break
                            default:
                                error "Unknown app target: ${app}"
                        }

                        def image = "${imageTag}:${env.IMAGE_TAG}"
                        def ecr_uri = "${env.AWS_ACCOUNT_ID}.dkr.ecr.${env.AWS_REGION}.amazonaws.com/prince-reg"

                        echo "Building Docker image for ${app} from context: app-code/${dockerContext}"
                        sh "docker build -t ${image} app-code/${dockerContext}"

                        echo "Pushing image: ${ecr_uri}:${imageTag} and latest"
                        sh """
                            docker tag ${image} ${ecr_uri}:${imageTag}
                            docker tag ${image} ${ecr_uri}:latest
                            docker push ${ecr_uri}:${imageTag}
                            docker push ${ecr_uri}:latest
                        """
                        
                        echo "✅ Successfully built and pushed ${app} as ${imageTag} to prince-reg repository"
                    }
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
                sh '''
                aws sns publish \
                  --region ${AWS_REGION} \
                  --topic-arn "${TOPIC_ARN}" \
                  --subject "✅ Jenkins ECR Deployment Success" \
                  --message "Jenkins successfully pushed image *${IMAGE_TAG}* to ECR for targets: ${BUILD_TARGETS} at $(date)"
                '''
            }
        }

        failure {
            withCredentials([[
                $class: 'AmazonWebServicesCredentialsBinding',
                credentialsId: 'PRINCE-AWS-CRED'
            ]]) {
                sh '''
                aws sns publish \
                  --region ${AWS_REGION} \
                  --topic-arn "${TOPIC_ARN}" \
                  --subject "❌ Jenkins ECR Deployment Failed" \
                  --message "Jenkins build failed for targets: ${BUILD_TARGETS} at $(date). Check logs for details."
                '''
            }
        }

        always {
            echo "Pipeline completed. Build targets were: ${env.BUILD_TARGETS}"
        }
    }
}