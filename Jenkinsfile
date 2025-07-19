pipeline {
    agent any

    parameters {
        choice(
            name: 'APP_TARGET',
            choices: [' ', 'mern-frontend', 'mern-backend-helloservice'],
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
                            targets << "mern-frontend"
                        }
                        if (changedFiles.any { it.startsWith("SampleMERNwithMicroservices/backend/helloService/") }) {
                            targets << "mern-backend-helloservice"
                        }

                        if (targets) {
                            env.BUILD_TARGETS = targets.join(',')
                        } else {
                            error("No relevant app changes detected. Skipping build.")
                        }
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
                        aws ecr get-login-password --region ${env.AWS_REGION} | \
                        docker login --username AWS --password-stdin ${env.AWS_ACCOUNT_ID}.dkr.ecr.${env.AWS_REGION}.amazonaws.com
                    """
                }
            }
        }

        stage('Build & Push Docker Images') {
            steps {
                script {
                    def targets = []

                    if (params.APP_TARGET?.trim()) {
                        targets = [params.APP_TARGET.trim()]
                    } else if (env.BUILD_TARGETS) {
                        targets = env.BUILD_TARGETS.split(',')
                    } else {
                        error("No build targets available.")
                    }

                    for (app in targets) {
                        def dockerContext = app == 'mern-frontend' ? 'SampleMERNwithMicroservices/frontend' :
                                            app == 'mern-backend-helloservice' ? 'SampleMERNwithMicroservices/backend/helloService' : null

                        if (!dockerContext) {
                            error "Unknown app target: ${app}"
                        }

                        def image = "${app}:${env.IMAGE_TAG}"
                        def ecr_uri = "${env.AWS_ACCOUNT_ID}.dkr.ecr.${env.AWS_REGION}.amazonaws.com/${app}"

                        echo "Building Docker image for ${app} from context: app-code/${dockerContext}"
                        sh "docker build -t ${image} app-code/${dockerContext}"

                        echo "Pushing image: ${ecr_uri}:${env.IMAGE_TAG} and latest"
                        sh """
                            docker tag ${image} ${ecr_uri}:${env.IMAGE_TAG}
                            docker tag ${image} ${ecr_uri}:latest
                            docker push ${ecr_uri}:${env.IMAGE_TAG}
                            docker push ${ecr_uri}:latest
                        """
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
                  --message "Jenkins pushed image *${IMAGE_TAG}* to ECR at $(date)"
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
                  --message "Jenkins build failed at $(date)"
                '''
            }
        }
    }
}
