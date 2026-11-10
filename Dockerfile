FROM python:3.12-slim
WORKDIR /app
COPY monitor ./monitor
COPY run.py .
RUN useradd --create-home pulse && mkdir data && chown pulse:pulse data
USER pulse
EXPOSE 8000
CMD ["python", "run.py", "--host", "0.0.0.0"]
