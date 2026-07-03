// Jest setup file for execution monitor tests

// Mock console methods to reduce noise in tests
global.console = {
    ...console,
    log: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
};

// Mock window.location
delete window.location;
window.location = {
    href: '',
    reload: jest.fn(),
};

// Mock setTimeout and clearTimeout
global.setTimeout = jest.fn((cb, delay) => {
    cb();
    return 1;
});

global.clearTimeout = jest.fn();

// Mock Event constructor
global.Event = class Event {
    constructor(type, options) {
        this.type = type;
        this.bubbles = options?.bubbles || false;
        this.cancelable = options?.cancelable || false;
    }
};
