# Docs Docker Deployment

This folder contains Docker configuration for running the docs project locally.

## Start

From this folder:

```bash
docker-compose up --build
```

Open: http://localhost:5173

## Stop

```bash
docker-compose down
```

## Notes

- Source code is mounted into the container, so Vite hot-reload works while editing files.
- Dependencies are stored in a named volume (`docs_node_modules`) to avoid host/container conflicts.