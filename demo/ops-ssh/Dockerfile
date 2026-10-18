FROM chronos-base:local
RUN useradd --create-home --shell /bin/sh probe && passwd -d probe
COPY sshd_config /etc/ssh/sshd_config
CMD ["/usr/sbin/sshd", "-D", "-e"]
