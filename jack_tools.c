/* Small stand-ins for jack_lsp, jack_connect and jack_disconnect.
 *
 * Homebrew's JACK no longer ships the example tools, so Beebo.app builds
 * this one program and installs it under all three names; it picks what to
 * do from the name it was started as.
 *
 *   jack_lsp                     list ports (exit 1 if no server is running)
 *   jack_connect A B             connect two ports
 *   jack_disconnect A B          disconnect two ports
 *   jack_check                   exit 0 if JACK's audio cycle is running,
 *                                3 if the server is up but no audio flows
 *
 *   cc -O2 -o jack_lsp jack_tools.c $(pkg-config --cflags --libs jack)
 */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <jack/jack.h>

static volatile unsigned long cycles = 0;

static int count_cycle(jack_nframes_t n, void* arg)
{
    (void)n; (void)arg;
    cycles++;
    return 0;
}

int main(int argc, char **argv)
{
    const char *name = strrchr(argv[0], '/');
    name = name ? name + 1 : argv[0];
    int is_lsp = strstr(name, "lsp") != NULL;
    int is_check = strstr(name, "check") != NULL;
    int is_disconnect = strstr(name, "disconnect") != NULL;

    if (!is_lsp && !is_check && argc != 3) {
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
    if (is_check) {
        /* count our own process callbacks for about a second */
        jack_set_process_callback(c, count_cycle, NULL);
        if (jack_activate(c)) {
            fprintf(stderr, "can't activate\n");
            jack_client_close(c);
            return 1;
        }
        for (int i = 0; i < 15 && cycles < 5; i++)
            usleep(100000);
        printf("audio cycles in test: %lu (sample rate %u, buffer %u)\n", cycles,
               jack_get_sample_rate(c), jack_get_buffer_size(c));
        rc = cycles >= 5 ? 0 : 3;
        jack_deactivate(c);
    } else if (is_lsp) {
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
