#!/bin/bash
# Replace environment variables in the nginx config
envsubst '$BACKEND_URL' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf

# Start nginx
exec nginx -g 'daemon off;'
```

### 6. Updated Dockerfile for frontend