# Lightweight High-Performance Nginx Web Server for HCM HUB Dashboard
FROM nginx:alpine

# Copy pre-compiled production build dist/
COPY dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
