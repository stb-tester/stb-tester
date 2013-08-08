#!/usr/bin/env perl

# Portable timeout command. Usage: timeout <secs> <command> [<args>...]

alarm shift @ARGV;
exec @ARGV;
print "timeout: command not found: @ARGV\n";
exit 1;
