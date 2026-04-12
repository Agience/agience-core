FROM ossrs/srs:5

COPY ./stream/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV STREAM_CONF=/usr/local/srs/conf/srs.conf

EXPOSE 1936 1985

ENTRYPOINT ["/entrypoint.sh"]
