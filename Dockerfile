FROM restgym/user-management-api:1.0.0
COPY carrier_bridge.py /carrier_bridge.py
COPY carrier_entrypoint.sh /carrier_entrypoint.sh
RUN chmod +x /carrier_entrypoint.sh
ENV DUSB04_UPSTREAM_HOST=127.0.0.1 DUSB04_UPSTREAM_PORT=8080
EXPOSE 9091
ENTRYPOINT ["/carrier_entrypoint.sh"]
