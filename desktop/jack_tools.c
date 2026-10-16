/* Small stand-ins for jack_lsp, jack_connect and jack_disconnect.
 *
 * Homebrew's JACK no longer ships the example tools, so Beebo.app builds
 * this one program and installs it under all three names; it picks what to
 * do from the name it was started as.
 *
 *   jack_lsp                     list ports (exit 1 if no server is running)
 *   jack_connect A B             connect two ports
 *   jack_disconnect A B          disconnect two ports
 *
 *   cc -O2 -o jack_lsp jack_tools.c $(pkg-config --cflags --libs jack)
 */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <jack/jack.h>

int main(int argc, char **argv)
{
    const char *name = strrchr(argv[0], '/');
    name = name ? name + 1 : argv[0];
    int is_lsp = strstr(name, "lsp") != NULL;
    int is_disconnect = strstr(name, "disconnect") != NULL;

    if (!is_lsp && argc != 3) {
        fprintf(stderr, "usage: %s <port> <port>\n", name);
        return 2;
    }

    jack_status_t status;
    jack_client_t *c = jack_client_open("beebo_tools", JackNoStartServer, &status);
    if (!c) {
        fprintf(stderr, "JACK server not running\n");
        return 1;
    }

    int rc = 0;
    if (is_lsp) {
        const char **ports = jack_get_ports(c, NULL, NULL, 0);
        for (int i = 0; ports && ports[i]; i++)
            printf("%s\n", ports[i]);
        if (ports)
            jack_free(ports);
    } else {
        jack_port_t *a = jack_port_by_name(c, argv[1]);
        jack_port_t *b = jack_port_by_name(c, argv[2]);
        if (!a || !b) {
            fprintf(stderr, "no such port: %s\n", a ? argv[2] : argv[1]);
            rc = 1;
        } else {
            /* accept either order, like jack_connect */
            const char *src = argv[1], *dst = argv[2];
            if (jack_port_flags(a) & JackPortIsInput) {
                src = argv[2];
                dst = argv[1];
            }
            int r = is_disconnect ? jack_disconnect(c, src, dst) : jack_connect(c, src, dst);
            if (r && r != EEXIST) {  /* already connected is fine */
                fprintf(stderr, "%s %s -> %s failed\n", is_disconnect ? "disconnect" : "connect", src, dst);
                rc = 1;
            }
        }
    }
    jack_client_close(c);
    return rc;
}
