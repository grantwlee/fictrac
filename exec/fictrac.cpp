/// FicTrac http://rjdmoore.net/fictrac/
/// \file       fictrac.cpp
/// \brief      FicTrac program.
/// \author     Richard Moore
/// \copyright  CC BY-NC-SA 3.0

#include "Logger.h"
#include "Trackball.h"
#include "timing.h"
#include "misc.h"
#include "fictrac_version.h"

#include <string>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <memory>
#include <vector>

#ifdef __linux__
#include <limits.h>
#include <unistd.h>
#elif _WIN32
#include <windows.h>
#endif

using namespace std;

/// Ctrl-c handling
bool _active = true;
void ctrlcHandler(int /*signum*/) { _active = false; }

namespace {

string quoteCommandArg(const string& value)
{
    string quoted = "\"";
    for (char ch : value) {
#ifdef _WIN32
        if (ch == '"') {
            quoted += '\\';
        }
#else
        if ((ch == '\\') || (ch == '"')) {
            quoted += '\\';
        }
#endif
        quoted += ch;
    }
    quoted += "\"";
    return quoted;
}

filesystem::path getExecutablePath(const char* argv0)
{
#ifdef __linux__
    char buf[PATH_MAX] = {0};
    ssize_t len = readlink("/proc/self/exe", buf, sizeof(buf) - 1);
    if (len > 0) {
        buf[len] = '\0';
        return filesystem::path(buf);
    }
#elif _WIN32
    char buf[MAX_PATH] = {0};
    DWORD len = GetModuleFileNameA(nullptr, buf, MAX_PATH);
    if (len > 0) {
        return filesystem::path(string(buf, len));
    }
#endif
    if ((argv0 != nullptr) && (argv0[0] != '\0')) {
        return filesystem::absolute(argv0);
    }
    return filesystem::current_path();
}

bool commandExists(const string& command)
{
#ifdef _WIN32
    const string null_device = "NUL";
#else
    const string null_device = "/dev/null";
#endif
    string probe = quoteCommandArg(command) + " --version >" + null_device + " 2>&1";
    return std::system(probe.c_str()) == 0;
}

string getPythonCommand()
{
#ifdef _WIN32
    const vector<string> candidates = {"python", "python3"};
#else
    const vector<string> candidates = {"python3", "python"};
#endif
    for (const auto& candidate : candidates) {
        if (commandExists(candidate)) {
            return candidate;
        }
    }
    return "";
}

int exportHtmlPlot(const char* argv0, const string& data_fn, double radius_cm)
{
    if (data_fn.empty()) {
        LOG_ERR("Error! No data file was produced for HTML plotting.");
        return -1;
    }

    filesystem::path data_path(data_fn);
    filesystem::path html_path = data_path;
    html_path.replace_extension(".html");

    filesystem::path exe_dir = getExecutablePath(argv0).parent_path();
    filesystem::path plotter_path = exe_dir / "FictracPlotter.py";
    if (!filesystem::exists(plotter_path)) {
        LOG_ERR("Error! Unable to locate FictracPlotter.py next to the FicTrac executable (%s).", plotter_path.string().c_str());
        return -1;
    }

    string python_cmd = getPythonCommand();
    if (python_cmd.empty()) {
        LOG_ERR("Error! Could not find a Python interpreter. Tried python3/python.");
        return -1;
    }

    string command = quoteCommandArg(python_cmd)
        + " "
        + quoteCommandArg(plotter_path.string())
        + " --input "
        + quoteCommandArg(data_path.string())
        + " --output "
        + quoteCommandArg(html_path.string())
        + " --radius-cm "
        + to_string(radius_cm);

    LOG("Generating HTML plot (%s) ..", html_path.string().c_str());
    int result = std::system(command.c_str());
    if (result != 0) {
        LOG_ERR("Error! HTML plot export failed with exit code %d.", result);
        return -1;
    }

    LOG("HTML plot written to %s.", html_path.string().c_str());
    return 0;
}

} // namespace


int main(int argc, char *argv[])
{
     PRINT("///");
     PRINT("/// FicTrac:\tA webcam-based method for generating fictive paths.\n///");
     PRINT("/// Usage:\tfictrac CONFIG_FN [-v LOG_VERBOSITY -s SRC_FN]\n///");
     PRINT("/// \tCONFIG_FN\tPath to input config file (defaults to config.txt).");
     PRINT("/// \tLOG_VERBOSITY\t[Optional] One of DBG, INF, WRN, ERR.");
     PRINT("/// \tSRC_FN\t\t[Optional] Override src_fn param in config file.");
     PRINT("///");
     PRINT("/// Version: %d.%d.%d (build date: %s)", FICTRAC_VERSION_MAJOR, FICTRAC_VERSION_MIDDLE, FICTRAC_VERSION_MINOR, __DATE__);
     PRINT("///\n");

	/// Parse args.
	string log_level = "info";
	string config_fn = "config.txt";
    string src_fn = "";
    bool do_stats = false;
	for (int i = 1; i < argc; ++i) {
		if ((string(argv[i]) == "--verbosity") || (string(argv[i]) == "-v")) {
			if (++i < argc) {
				log_level = argv[i];
			}
			else {
                LOG_ERR("-v/--verbosity requires one argument (debug < info (default) < warn < error)!");
				return -1;
			}
        }
        else if (string(argv[i]) == "--stats") {
            do_stats = true;
        }
        else if ((string(argv[i]) == "--src") || (string(argv[i]) == "-s")) {
            if (++i < argc) {
				src_fn = argv[i];
			}
			else {
                LOG_ERR("-s/--src requires one argument!");
				return -1;
			}
        }
        else {
            config_fn = argv[i];
		}
	}

    /// Set logging level.
    Logger::setVerbosity(log_level);

	// Catch cntl-c
    signal(SIGINT, ctrlcHandler);

	/// Set high priority (when run as SU).
    if (!SetProcessHighPriority()) {
        LOG_ERR("Error! Unable to set process priority!");
    } else {
        LOG("Set process priority to HIGH!");
    }

    unique_ptr<Trackball> tracker = make_unique<Trackball>(config_fn, src_fn);
    bool startup_error = tracker->hadError();

    /// Now Trackball has spawned our worker threads, we set this thread to low priority.
    SetThreadNormalPriority();

    /// Wait for tracking to finish.
    while (tracker->isActive()) {
        if (!_active) {
            tracker->terminate();
        }
        ficsleep(250);
    }

    if (!startup_error) {
        /// Save the eventual template to disk.
        tracker->writeTemplate();

        /// If we're running in test mode, print some stats.
        if (do_stats) {
            tracker->dumpStats();
        }
    }

    bool plot_html = tracker->shouldPlotHtml();
    double plot_radius_cm = tracker->getPlotRadiusCm();
    string data_fn = tracker->getDataLogPath();

    /// Try to force release of all objects.
    tracker.reset();

    int exit_code = startup_error ? -1 : 0;
    if ((exit_code == 0) && plot_html) {
        exit_code = exportHtmlPlot(argv[0], data_fn, plot_radius_cm);
    }

    /// Wait a bit before exiting...
    ficsleep(250);

    //PRINT("\n\nHit ENTER to exit..");
    //getchar_clean();
    return exit_code;
}
