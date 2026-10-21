import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ plugins:[react()], server:{ host:'127.0.0.1',port:5174,
proxy:{ '/api':{target:process.env.VITE_BACKEND ?? 'http://localhost:8081',changeOrigin:true}, '/health':{target:process.env.VITE_BACKEND ?? 'http://localhost:8081'} } }, build:{outDir:'../static',emptyOutDir:true} });
