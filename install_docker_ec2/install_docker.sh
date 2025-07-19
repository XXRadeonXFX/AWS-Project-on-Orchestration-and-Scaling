#!/bin/bash
# Update package list
apt-get update -y

# Install required packages
apt-get install -y apt-transport-https ca-certificates curl software-properties-common gnupg

# Add Docker's GPG key and repo
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update again and install Docker
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io

# Start Docker
systemctl start docker
systemctl enable docker

# Add current user to docker group
usermod -aG docker $USER
