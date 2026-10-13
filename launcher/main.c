// Executable of WhisperUI.app, used by the LaunchAgent.
//
// macOS attributes mic access to the "responsible" app of a process tree. Started directly by
// launchd, that would be Homebrew's Python.app, which has no NSMicrophoneUsageDescription, so
// the mic is denied without a prompt. Running run.sh as our child makes WhisperUI.app (with its
// own usage description) the responsible app. We forward termination signals and exit with the
// child's status, so launchd's KeepAlive restarts after a crash but not after Quit.
#include <errno.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>

extern char **environ;
static pid_t child = -1;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

int main(void) {
    // <project>/build/WhisperUI.app/Contents/MacOS/WhisperUI -> <project>/run.sh
    char exe[PATH_MAX], dir[PATH_MAX], run_sh[PATH_MAX];
    uint32_t size = sizeof exe;
    if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, dir)) return 1;
    for (int i = 0; i < 5; i++) *strrchr(dir, '/') = '\0';
    snprintf(run_sh, sizeof run_sh, "%s/run.sh", dir);

    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    signal(SIGHUP, forward);
    char *args[] = {run_sh, NULL};
    int err = posix_spawn(&child, run_sh, NULL, NULL, args, environ);
    if (err) {
        fprintf(stderr, "WhisperUI: cannot start %s: %s\n", run_sh, strerror(err));
        return 1;
    }
    int status;
    while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}
