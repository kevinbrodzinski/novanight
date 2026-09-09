FROM restgym/market-api:1.0.0
COPY carrier_bridge.py /carrier_bridge.py
COPY carrier_entrypoint.sh /carrier_entrypoint.sh
RUN chmod +x /carrier_entrypoint.sh
ENV DUSB04_UPSTREAM_HOST=127.0.0.1
EXPOSE 9091
ENTRYPOINT ["/carrier_entrypoint.sh"]
