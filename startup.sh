#!/bin/bash

# Render startup script for Streamlit
streamlit run streamlit_app.py \
  --server.port=${PORT:-8501} \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false