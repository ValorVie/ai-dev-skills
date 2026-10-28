ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
COPY bd dolt getfacl setfacl fuser /usr/local/bin/
COPY libacl.so.1 /usr/local/lib/libacl.so.1
ENV LD_LIBRARY_PATH=/usr/local/lib
ENTRYPOINT []
CMD ["/bin/bash"]
