#!/bin/bash
set -e

echo "📦 Updating packages..."
apt update -y

echo "📦 Installing unzip and curl..."
apt install -y unzip curl

echo "⬇️ Downloading AWS CLI v2..."
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"

echo "🗂️ Unzipping installer..."
unzip awscliv2.zip

echo "⚙️ Installing AWS CLI..."
sudo ./aws/install

echo "✅ Cleaning up..."
rm -rf aws awscliv2.zip

echo "✅ AWS CLI Installed:"
aws --version
