FROM node:20-alpine

WORKDIR /app

COPY package.json ./
# package-lock.json is optional on first run; copy when present.
COPY package-lock.jso[n] ./

RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
