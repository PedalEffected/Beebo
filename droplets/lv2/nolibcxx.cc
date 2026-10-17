// Minimal C++ runtime support so the pedal build needs no C++ standard
// library at all: Droplets only uses new/delete, which map to malloc/free.
#include <cstdlib>
#include <new>
void* operator new(std::size_t n) { return std::malloc(n ? n : 1); }
void* operator new[](std::size_t n) { return std::malloc(n ? n : 1); }
void* operator new(std::size_t n, const std::nothrow_t&) noexcept { return std::malloc(n ? n : 1); }
void* operator new[](std::size_t n, const std::nothrow_t&) noexcept { return std::malloc(n ? n : 1); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }
extern "C" void __cxa_pure_virtual() { std::abort(); }
