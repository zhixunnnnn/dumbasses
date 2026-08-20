# Pinned to the stable unauthenticated REST contract used by the app adapter.
FROM unclecode/crawl4ai:0.8.0

# The upstream image starts gunicorn with `--bind 0.0.0.0:11235`, which listens on
# IPv4 only. Railway's internal network — used by both the private-network
# hostname and the healthcheck behind the public domain — is IPv6, so an
# IPv4-only listener is unreachable and every request returns 502 while the
# container itself looks perfectly healthy.
#
# `[::]` is a dual-stack socket (net.ipv6.bindv6only defaults to 0), so this keeps
# working for plain IPv4 clients such as docker-compose.
USER root
RUN sed -i 's|--bind 0.0.0.0:11235|--bind [::]:11235|' /app/supervisord.conf \
    && grep -q -- '--bind \[::\]:11235' /app/supervisord.conf
USER appuser

EXPOSE 11235
