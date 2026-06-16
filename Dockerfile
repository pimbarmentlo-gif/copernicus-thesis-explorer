FROM ghcr.io/astral-sh/uv:python3.11-alpine

WORKDIR /cte

# RUN apk update
# RUN apk upgrade
# RUN apk add git

ADD . .

EXPOSE 8501

ENV UV_LINK_MODE=copy

RUN --mount=type=cache,target=/root/.cache/ uv sync 

ENV PATH="/cte/.venv/bin/:$PATH"

# CMD ["/bin/bash"]
CMD [ "streamlit", "run", "dashboard.py" ]