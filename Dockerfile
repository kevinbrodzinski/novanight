FROM restgym/market-api:1.0.0
COPY carrier_bridge.py /carrier_bridge.py
COPY carrier_entrypoint.sh /carrier_entrypoint.sh
RUN chmod +x /carrier_entrypoint.sh
ENV DUSB04_UPSTREAM_HOST=127.0.0.1 DUSB04_UPSTREAM_PORT=9090 TOOL=DUSB04 RUN=market
EXPOSE 9091
ENTRYPOINT ["/carrier_entrypoint.sh"]
CMD ["/bin/sh","-c","mkdir -p /results/$API/$TOOL/$RUN && sh /infrastructure/jacoco/collect-coverage-interval.sh & mitmdump -p 9090 --mode reverse:http://localhost:8080/ -s /infrastructure/mitmproxy/store-interactions.py -s /api/auth.py & java -javaagent:/infrastructure/jacoco/org.jacoco.agent-0.8.7-runtime.jar=includes=*,output=tcpserver,port=12345,address=* -Dfile.encoding=UTF-8 -jar /api/market-sut.jar"]
