# Docker and Render deployment

This file describes how to build and run the project's Docker image locally and how to deploy it to Render using the repository Dockerfile.

Local build & run

1. Build the image:

```powershell
docker build -t port-forwarding-server .
```

2. Run locally (maps container port to local port 5000):

```powershell
docker run --rm -p 5000:5000 -e PORT=5000 port-forwarding-server
```

The app will be accessible at http://localhost:5000

Deploying to Render (Docker)

1. Push this repository to your Git provider (GitHub/GitLab/Bitbucket).
2. On Render, create a new "Web Service" and select "Docker" as the deployment method.
3. Connect your repository and select the branch (for example `main`). Render will detect the `Dockerfile` and build the image.
4. Render provides a `PORT` environment variable to the container at runtime. The app reads `PORT` from the environment. No additional start command is required.

Notes
- The Docker image installs `eventlet` to provide a production-ready async server for Flask-SocketIO. This prevents the "Werkzeug web server is not designed to run in production" error on Render.
- Keep secrets (DB credentials, SECRET_KEY) as Render environment variables rather than committing them to source.
 
