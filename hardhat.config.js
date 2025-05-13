/** @type import('hardhat/config').HardhatUserConfig */
// hardhat.config.js
require("@nomicfoundation/hardhat-toolbox");

module.exports = {
  solidity: "0.8.24",
  networks: {
    hardhat: { chainId: 31337 },
  },
};
