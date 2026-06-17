FROM ghcr.io/astral-sh/uv:python3.11-alpine

USER 1002860000:1002860000

WORKDIR /cte

# RUN apk update
# RUN apk upgrade
# RUN apk add git

ADD . .

EXPOSE 8501

ENV UV_LINK_MODE=copy

USER root:root
RUN --mount=type=cache,target=/root/.cache/ uv sync 
RUN chown -hR 1002860000:1002860000 /cte 
USER 1002860000:1002860000

ENV PATH="/cte/.venv/bin/:$PATH"

# CMD ["/bin/bash"]
CMD [ "streamlit", "run", "dashboard/dashboard.py" ]