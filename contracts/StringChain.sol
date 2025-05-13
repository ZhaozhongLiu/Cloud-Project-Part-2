// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract StringChain {
    string[] private _list;
    event DataAdded(uint256 indexed id, string data);

    function addData(string calldata data) external {
        _list.push(data);
        emit DataAdded(_list.length - 1, data);
    }

    function getAll() external view returns (string[] memory) {
        return _list;
    }
}
